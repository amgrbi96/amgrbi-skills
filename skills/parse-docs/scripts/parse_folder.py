#!/usr/bin/env python3
"""
parse-docs orchestrator — folder and all-methods batch modes.

Routes each file in a directory independently by type and runs one tool
(mode: folder) or every applicable tool (mode: all) per document, into:

    output/<document-name>/<tool-name>/...

Local tools always run when installed. mineru (cloud) runs only when BOTH
--mineru is passed AND tokens are configured — validated first with the
mineru script's own --dry-run, which works offline.

Resume: a document+tool whose output already exists (and is non-empty for
the local text tools) is skipped, so re-runs never redo work or re-spend
mineru quota.

Stdlib only. Exit codes: 0 = all requested work succeeded or was skipped,
1 = any file failed or no parsable input found.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TOOLS = {
    "pdf-to-markdown": SKILL_DIR / ".." / "pdf-to-markdown" / "bin" / "pdf-to-markdown",
    "pymupdf": SKILL_DIR / ".." / "pymupdf-pdf" / "scripts" / "pymupdf_parse.py",
    "mineru": SKILL_DIR / ".." / "mineru" / "scripts" / "mineru_v2.py",
}
MINERU_TOKENS_FILE = SKILL_DIR / ".." / "mineru" / "tokens.txt"

# Extension → tools that can parse it (order = all-methods run order).
MINERU_EXTS = {".pdf", ".docx", ".pptx", ".jpg", ".jpeg", ".png"}
LITEPARSE_ONLY_EXTS = {
    ".docm", ".odt", ".rtf", ".pptm", ".odp",             # Office, mineru can't
    ".xlsx", ".xlsm", ".ods", ".csv", ".tsv",             # spreadsheets
    ".gif", ".bmp", ".tiff", ".webp", ".svg",             # images mineru can't
}
PDF_EXTS = {".pdf"}


def applicable_tools(ext: str) -> list[str]:
    """Tools that support this extension, in run order."""
    if ext in PDF_EXTS:
        return ["pdf-to-markdown", "pymupdf", "liteparse", "mineru"]
    if ext in MINERU_EXTS:
        return ["liteparse", "mineru"]
    if ext in LITEPARSE_ONLY_EXTS:
        return ["liteparse"]
    return []


def choose_tool(ext: str, prefer: str, available: dict) -> str | None:
    """Folder mode: pick the single best installed tool for this extension."""
    candidates = {
        "speed": {
            ".pdf": ["pdf-to-markdown", "pymupdf", "liteparse", "mineru"],
            "*": ["liteparse", "mineru"],
        },
        "accuracy": {
            ".pdf": ["mineru", "liteparse", "pymupdf", "pdf-to-markdown"],
            "*": ["mineru", "liteparse"],
        },
    }[prefer]
    for tool in candidates.get(ext, candidates["*"]):
        if available.get(tool):
            return tool
    return None


def detect_tools(mineru_wanted: bool) -> dict:
    """Which tools are usable on this machine right now."""
    available = {
        "pdf-to-markdown": os.access(TOOLS["pdf-to-markdown"], os.X_OK),
        "pymupdf": TOOLS["pymupdf"].is_file() and _pymupdf_importable(),
        "liteparse": shutil.which("lit") is not None,
    }
    # mineru: script present, this interpreter is 3.10+ (script requirement),
    # and at least one token source configured.
    tokens = _mineru_tokens()
    available["mineru"] = (
        TOOLS["mineru"].is_file()
        and sys.version_info >= (3, 10)
        and bool(tokens)
        and mineru_wanted
    )
    return available


def _pymupdf_importable() -> bool:
    try:
        import pymupdf  # noqa: F401
        return True
    except ImportError:
        return False


def _mineru_tokens() -> list[str]:
    tokens = []
    for env in ("MINERU_TOKENS", "MINERU_TOKEN"):
        for t in os.environ.get(env, "").split(","):
            t = t.strip()
            if t and t not in tokens:
                tokens.append(t)
    if MINERU_TOKENS_FILE.is_file():
        try:
            for line in MINERU_TOKENS_FILE.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line not in tokens:
                    tokens.append(line)
        except OSError:
            pass
    return tokens


def mineru_dry_run(sample: Path) -> tuple[bool, str]:
    """Validate the mineru path offline via its own --dry-run on one file.

    Returns (ok, note). Catches bad interpreter, missing deps, exhausted
    token pool — all without network.
    """
    cmd = [sys.executable, str(TOOLS["mineru"]), "--file", str(sample),
           "--output", "/tmp/parse-docs-mineru-check", "--dry-run"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"mineru dry-run failed to execute: {e}"
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        first = next((l for l in out.splitlines() if l.strip()), "unknown error")
        return False, f"mineru dry-run exit {r.returncode}: {first}"
    m = re.search(r"(\d+) active token", out)
    note = f"{m.group(1)} active token(s)" if m else "tokens ok"
    return True, note


def pdf_page_counts(files: list[Path]) -> dict:
    """Exact PDF page counts when pymupdf is importable, else empty."""
    try:
        import pymupdf
    except ImportError:
        return {}
    counts = {}
    for f in files:
        if f.suffix.lower() == ".pdf":
            try:
                with pymupdf.open(f) as doc:
                    counts[f.name] = doc.page_count
            except Exception:
                pass
    return counts


# --- per-tool run/skip logic -------------------------------------------------

def out_dir(output: Path, doc: str, tool: str) -> Path:
    return output / doc / tool


def plan_runs(files: list[Path], mode: str, prefer: str, available: dict,
              output: Path, fmt: str) -> list[dict]:
    """Build the (file → tool) run plan with resume skips applied."""
    runs = []
    for f in files:
        ext = f.suffix.lower()
        tools = applicable_tools(ext)
        if not tools:
            runs.append({"file": f, "tool": None, "skip": "unsupported format"})
            continue
        if mode == "folder":
            tool = choose_tool(ext, prefer, available)
            tools_to_run = [tool] if tool else []
        else:
            tools_to_run = [t for t in tools if available.get(t)]
        if not tools_to_run:
            missing = [t for t in tools if not available.get(t)]
            runs.append({"file": f, "tool": None,
                         "skip": f"no applicable tool installed/enabled ({', '.join(missing)})"})
            continue
        for tool in tools_to_run:
            runs.append({"file": f, "tool": tool, "skip": None})
    return runs


def already_done(f: Path, tool: str, output: Path, fmt: str) -> str | None:
    """Return the existing output path if this doc+tool is done, else None."""
    doc, stem = f.name, f.stem
    d = out_dir(output, doc, tool)
    if tool == "pdf-to-markdown":
        # .scanned-skip records a known-empty (scanned) result — see run_tool
        if (d / ".scanned-skip").is_file():
            return str(d / ".scanned-skip")
        md = d / f"{stem}.md"
        return str(md) if md.is_file() and md.stat().st_size > 10 else None
    if tool == "pymupdf":
        md = d / stem / "output.md"
        return str(md) if md.is_file() else None
    if tool == "liteparse":
        out = d / f"{stem}.{fmt}"
        return str(out) if out.is_file() and out.stat().st_size > 0 else None
    if tool == "mineru":
        return str(d / stem) if (d / stem).is_dir() else None
    return None


def run_tool(f: Path, tool: str, output: Path, fmt: str) -> tuple[bool, str]:
    """Run one tool on one file. Returns (ok, detail)."""
    doc, stem = f.name, f.stem
    d = out_dir(output, doc, tool)
    d.mkdir(parents=True, exist_ok=True)

    if tool == "pdf-to-markdown":
        md = d / f"{stem}.md"
        r = subprocess.run([str(TOOLS[tool]), str(f), str(md)],
                           capture_output=True, text=True)
        if r.returncode == 0 and md.is_file() and md.stat().st_size <= 10:
            # Deterministic: scanned PDFs yield ~2 bytes with exit 0. Mark it
            # so resume skips this doc+tool instead of failing on every re-run.
            (d / ".scanned-skip").write_text(
                "empty output — scanned PDF; use the liteparse/mineru output\n")
            return False, "empty output — scanned PDF (recorded; skipped on re-runs)"
        if r.returncode != 0 or not md.is_file() or md.stat().st_size <= 10:
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            why = detail[-1] if detail else "no output"
            return False, why
        return True, str(md)

    if tool == "pymupdf":
        r = subprocess.run(
            [sys.executable, str(TOOLS[tool]), str(f), "--format", "md",
             "--outroot", str(d)],
            capture_output=True, text=True)
        md = d / stem / "output.md"
        if r.returncode != 0 or not md.is_file():
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            return False, detail[-1] if detail else "no output"
        return True, str(md)

    if tool == "liteparse":
        out = d / f"{stem}.{fmt}"
        format_flag = "markdown" if fmt == "md" else "text"
        r = subprocess.run(
            ["lit", "parse", str(f), "--format", format_flag, "-q", "-o", str(out)],
            capture_output=True, text=True)
        if r.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            return False, (detail[-1] if detail else "empty output") + \
                " (empty OCR = degraded scan; try mineru)"
        return True, str(out)

    if tool == "mineru":
        r = subprocess.run(
            [sys.executable, str(TOOLS[tool]), "--file", str(f),
             "--output", str(d)],
            capture_output=True, text=True)
        done = (d / stem).is_dir()
        if r.returncode != 0 or not done:
            detail = (r.stderr or r.stdout or "").strip().splitlines()
            return False, detail[-1] if detail else "mineru run failed"
        return True, str(d / stem)

    return False, f"unknown tool {tool}"


def fallback_tool(f: Path, failed_tool: str, available: dict) -> str | None:
    """Folder-mode fallback when the chosen tool produced nothing."""
    if failed_tool == "pdf-to-markdown" and available.get("liteparse"):
        return "liteparse"  # empty output = scanned PDF; liteparse has OCR
    return None


def main():
    parser = argparse.ArgumentParser(
        description="parse-docs batch orchestrator: route each file in a "
                    "directory to the right parser (folder mode) or run every "
                    "applicable parser (all mode).",
        epilog="Output layout: OUTPUT/<document-name>/<tool-name>/… "
               "Documents whose tool output already exists are skipped (resume).",
    )
    parser.add_argument("input", help="Input directory")
    parser.add_argument("--output", default="./output", help="Output root (default: ./output)")
    parser.add_argument("--mode", choices=["folder", "all"], default="folder",
                        help="folder = one best tool per file (default); all = every applicable tool")
    parser.add_argument("--prefer", choices=["speed", "accuracy"], default="speed",
                        help="folder mode routing bias (default: speed)")
    parser.add_argument("--format", choices=["md", "txt"], default="md",
                        help="liteparse output format (default: md)")
    parser.add_argument("--mineru", action="store_true",
                        help="allow cloud mineru runs (needs tokens; quota is spent)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the routing plan, resume skips, and mineru quota — run nothing")
    args = parser.parse_args()

    input_dir = Path(args.input).expanduser()
    if not input_dir.is_dir():
        print(f"❌ not a directory: {input_dir}")
        sys.exit(1)
    output = Path(args.output).expanduser()

    files = sorted(f for f in input_dir.iterdir()
                   if f.is_file() and not f.name.startswith("."))
    if not files:
        print(f"❌ no files in {input_dir}")
        sys.exit(1)

    available = detect_tools(args.mineru)
    missing = [t for t, ok in available.items() if not ok]
    if missing:
        reasons = {"pdf-to-markdown": "binary missing",
                   "pymupdf": "script or pymupdf package missing",
                   "liteparse": "`lit` not on PATH",
                   "mineru": "no --mineru flag, no tokens, script missing, or Python < 3.10"}
        print("⚠️  unavailable tools (files route to what's installed):")
        for t in missing:
            print(f"   {t}: {reasons[t]}")

    runs = plan_runs(files, args.mode, args.prefer, available, output, args.format)

    # mineru quota gate — verify offline with the mineru script's own --dry-run
    mineru_runs = [r for r in runs if r["tool"] == "mineru"]
    if mineru_runs:
        sample = mineru_runs[0]["file"]
        ok, note = mineru_dry_run(sample)
        if not ok:
            print(f"⚠️  mineru disabled for this run: {note}")
            for r in mineru_runs:
                r["tool"], r["skip"] = None, "mineru failed pre-flight"
        else:
            pages = pdf_page_counts([r["file"] for r in mineru_runs])
            known = sum(pages.values())
            n_pdf = sum(1 for r in mineru_runs if r["file"].suffix.lower() == ".pdf")
            tokens = _mineru_tokens()
            print(f"☁️  mineru quota: {len(mineru_runs)} file(s) "
                  f"({n_pdf} PDF(s), {known} pages counted"
                  f"{', page count unknown for non-PDFs' if len(mineru_runs) > n_pdf else ''}) "
                  f"vs {len(tokens)} token(s) × 1000 pages/day. "
                  f"Files are capped at 200 MB / 200 pages each ({note}).")

    # --- print plan / execute ---
    print(f"\n📂 {input_dir} → {output}  (mode: {args.mode}"
          + (f", prefer: {args.prefer}" if args.mode == "folder" else "") + ")")
    results = {"done": [], "skip_plan": [], "skip_resume": [], "fail": []}

    for r in runs:
        f = r["file"]
        if r["tool"] is None:
            results["skip_plan"].append((f.name, r["skip"]))
            continue
        done = already_done(f, r["tool"], output, args.format)
        if done:
            results["skip_resume"].append((f.name, r["tool"]))
            continue
        if args.dry_run:
            print(f"  ▶ {f.name} → {r['tool']}  ({out_dir(output, f.name, r['tool'])})")
            continue
        ok, detail = run_tool(f, r["tool"], output, args.format)
        mark = "✅" if ok else "❌"
        print(f"  {mark} {f.name} → {r['tool']}" + ("" if ok else f"  — {detail}"))
        if ok:
            results["done"].append((f.name, r["tool"]))
            continue
        # folder mode: one-shot fallback for scanned PDFs (empty fast output)
        if args.mode == "folder":
            fb = fallback_tool(f, r["tool"], available)
            if fb and not already_done(f, fb, output, args.format):
                ok2, detail2 = run_tool(f, fb, output, args.format)
                print(f"  {'✅' if ok2 else '❌'} {f.name} → {fb} (fallback)"
                      + ("" if ok2 else f"  — {detail2}"))
                if ok2:
                    results["done"].append((f.name, fb))
        if (out_dir(output, f.name, r["tool"]) / ".scanned-skip").is_file():
            results["skip_plan"].append(
                (f.name, f"{r['tool']}: scanned PDF (empty output) — skipped on re-runs"))
        else:
            results["fail"].append((f.name, r["tool"]))

    # --- summary ---
    print(f"\n{'=' * 60}")
    if args.dry_run:
        n_run = sum(1 for r in runs if r["tool"] and not already_done(r["file"], r["tool"], output, args.format))
        print(f"📋 Dry run — would run {n_run} tool run(s), "
              f"skip {len(results['skip_resume'])} (resume), "
              f"skip {len(results['skip_plan'])} (no tool).")
    else:
        print(f"✅ parsed: {len(results['done'])}  "
              f"⏭️ resumed/skipped: {len(results['skip_resume'])}  "
              f"🚫 unroutable: {len(results['skip_plan'])}  "
              f"❌ failed: {len(results['fail'])}")
    for name, why in results["skip_plan"]:
        print(f"   🚫 {name}: {why}")
    for name, tool in results["fail"]:
        print(f"   ❌ {name}: {tool} failed")

    tree = sorted({out_dir(output, name, tool) for name, tool
                   in results["done"] + results["skip_resume"]})
    if tree and not args.dry_run:
        print(f"\n📁 outputs under {output}/:")
        for d in tree[:10]:
            print(f"   {d.relative_to(output)}")
        if len(tree) > 10:
            print(f"   … and {len(tree) - 10} more")
    if results["fail"] and not args.dry_run:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
