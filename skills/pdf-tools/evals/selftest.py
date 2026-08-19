#!/usr/bin/env python3
"""Offline self-test for the pdf-tools skill — no network required.

Run after changing SKILL.md or any file under references/:

    python3 evals/selftest.py

Covers, in order:
1. Structure: SKILL.md reference links match the references/ directory
   (no dead links, no orphan files), frontmatter on every reference.
2. Doc drift: deprecated patterns are gone (`networkidle0` in setContent,
   `import fitz`, `scripts/*` invocations, `ignoreEncryption` without its
   never-decrypts warning), the parse-docs routing note still matches the
   sibling skill, and the prerequisites Check block runs and reports every
   expected tool.
3. Examples: extracts every filename-headered script from the references
   (`// x.js — node x.js ...` / `# x.py — python x.py ...`) and executes
   it against fixtures — pdf-lib in a scratch npm project, pymupdf
   with the current interpreter, ghostscript if installed. Missing deps
   SKIP with an install hint; they never FAIL.

Puppeteer/Playwright examples are deliberately not executed (they need a
Chromium download); they are covered by the static drift checks only.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
SKILL_MD = SKILL_DIR / "SKILL.md"
PARSE_DOCS = SKILL_DIR.parent / "parse-docs" / "SKILL.md"

PASSED, FAILED, SKIPPED = [0], [0], [0]

# References whose examples must contain executable, filename-headered
# scripts (browser-dependent high-fidelity-generation.md is exempt).
EXPECT_HEADERED = {
    "batch-and-accessibility.md",
    "form-filling.md",
    "images-and-optimization.md",
    "legacy-utilities.md",
    "page-operations.md",
    "watermarking-and-overlays.md",
}

EXPECTED_PREREQ_NAMES = {
    "pdf-lib", "puppeteer", "unpdf", "bullmq", "@signpdf/signpdf",
    "pymupdf", "pdfplumber",
    "qpdf", "gs", "verapdf", "pdftotext", "exiftool", "redis-server",
}

PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

FIELDS_JSON = {
    "form_fields": [
        {
            "page_number": 1,
            "entry_bounding_box": [100, 600, 400, 650],
            "entry_text": {"text": "Johnson", "font_size": 14},
        }
    ]
}

FIELD_VALUES_JSON = [
    {"field_id": "last_name", "value": "Simpson"},
    {"field_id": "gender_group", "value": "Male"},
]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print(f"PASS {name}")
    else:
        FAILED[0] += 1
        print(f"FAIL {name}" + (f" — {detail}" if detail else ""))


def skip(name, why):
    SKIPPED[0] += 1
    print(f"SKIP {name} — {why}")


def section(title):
    print(f"\n===== {title} =====")


def all_md():
    return [SKILL_MD, *sorted(REFS.glob("*.md"))]


# ---------------------------------------------------------------------------
# 1. Structure
# ---------------------------------------------------------------------------
def structure_tests():
    section("structure")

    linked = set(re.findall(r"references/([a-z0-9-]+\.md)", SKILL_MD.read_text()))
    on_disk = {p.name for p in REFS.glob("*.md")}
    check("structure: no dead reference links", linked <= on_disk,
          f"linked but missing: {sorted(linked - on_disk)}")
    check("structure: no orphan reference files", on_disk <= linked,
          f"on disk but not linked: {sorted(on_disk - linked)}")

    for md in REFS.glob("*.md"):
        text = md.read_text()
        ok = text.startswith("---\n") and "title:" in text.split("---")[1] \
            and "description:" in text.split("---")[1]
        check(f"structure: frontmatter in {md.name}", ok)

    body_lines = len(SKILL_MD.read_text().splitlines())
    check("structure: SKILL.md body under 250 lines", body_lines < 250,
          f"{body_lines} lines")

    fm = SKILL_MD.read_text().split("---")[1]
    check("structure: SKILL.md name and version",
          "name: pdf-tools" in fm and re.search(r"version: '\d+\.\d+'", fm))


# ---------------------------------------------------------------------------
# 2. Doc drift
# ---------------------------------------------------------------------------
def drift_tests():
    section("doc drift")

    corpus = {p.name: p.read_text() for p in all_md()}

    check("drift: no networkidle0 anywhere",
          not any("networkidle0" in t for t in corpus.values()))
    check("drift: no deprecated 'import fitz'",
          not any(re.search(r"import fitz\b|\bfitz\.", t) for t in corpus.values()))
    check("drift: no scripts/ invocations",
          not any(re.search(r"python3? +scripts?/", t) for t in corpus.values()))

    for name, text in corpus.items():
        if "ignoreEncryption" in text:
            check(f"drift: ignoreEncryption warned in {name}",
                  "never decrypts" in text or "suppresses" in text.lower())

    # routing note vs the sibling parse-docs skill
    if PARSE_DOCS.exists():
        pd = PARSE_DOCS.read_text()
        tools = ["pdf-to-markdown", "pymupdf-pdf", "liteparse", "mineru"]
        check("drift: routing targets exist in parse-docs",
              all(t in pd for t in tools),
              f"missing in parse-docs: {[t for t in tools if t not in pd]}")
        check("drift: SKILL.md routes extraction to parse-docs",
              "parse-docs" in corpus["SKILL.md"]
              and all(t in corpus["SKILL.md"] for t in tools))
    else:
        skip("drift: parse-docs cross-check", "sibling skill not installed")

    # every execution-backed reference has at least one headered script
    for name in sorted(EXPECT_HEADERED):
        text = corpus[name]
        has = re.search(r"^// \S+\.js — node|^# \S+\.py — python", text, re.M)
        check(f"drift: runnable script present in {name}", bool(has))


# ---------------------------------------------------------------------------
# 3. Prerequisites Check block (executed verbatim from SKILL.md)
# ---------------------------------------------------------------------------
def prereq_block_tests():
    section("prereq block")

    m = re.search(r"### Check\s+```bash\n(.*?)```", SKILL_MD.read_text(), re.S)
    if not m:
        check("prereq: Check block found in SKILL.md", False)
        return
    check("prereq: Check block found in SKILL.md", True)

    with tempfile.TemporaryDirectory(prefix="pdf-tools-prereq-") as td:
        script = Path(td) / "check.sh"
        script.write_text(m.group(1))
        proc = subprocess.run(["bash", str(script)], capture_output=True,
                              text=True, timeout=120)
        reported = dict(re.findall(r"^(\S+): (ok|MISSING)$", proc.stdout, re.M))
        check("prereq: check block exits 0", proc.returncode == 0,
              proc.stderr[:200])
        check("prereq: every expected tool reported",
              EXPECTED_PREREQ_NAMES <= set(reported),
              f"not reported: {sorted(EXPECTED_PREREQ_NAMES - set(reported))}")


# ---------------------------------------------------------------------------
# 4. Execute the documented examples
# ---------------------------------------------------------------------------
def extract_scripts():
    """Pull filename-headered scripts out of the references."""
    scripts = {}
    for md in sorted(REFS.glob("*.md")):
        for block in re.findall(r"```(js|javascript|python)\n(.*?)```",
                                md.read_text(), re.S):
            lang, code = block
            header = re.match(r"(?://|#) (\S+\.(?:js|py)) — ", code)
            if header:
                scripts[header.group(1)] = (lang, code)
    return scripts


def make_fixtures(dirpath):
    """input.pdf (3 pages), secret.pdf, stamp.pdf, images, JSON files."""
    import pymupdf

    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 300, 100), f"Page {i + 1}")
    doc.save(dirpath / "input.pdf")

    secret = pymupdf.open()
    secret.new_page().insert_textbox(
        pymupdf.Rect(50, 50, 400, 100), "SSN: 123-45-6789")
    secret.save(dirpath / "secret.pdf")

    stamp = pymupdf.open()
    stamp.new_page(width=200, height=100).insert_textbox(
        pymupdf.Rect(20, 30, 180, 80), "APPROVED")
    stamp.save(dirpath / "stamp.pdf")

    (dirpath / "fields.json").write_text(json.dumps(FIELDS_JSON))
    (dirpath / "field_values.json").write_text(json.dumps(FIELD_VALUES_JSON))
    (dirpath / "logo.png").write_bytes(__import__("base64").b64decode(PNG_1PX))


FILLABLE_FIXTURE_JS = """
import { PDFDocument } from 'pdf-lib';
import * as fs from 'node:fs/promises';
const d = await PDFDocument.create();
const p = d.addPage([595.28, 841.89]);
const f = d.getForm();
f.createTextField('last_name').addToPage(p);
const g = f.createRadioGroup('gender_group');
g.addOptionToPage('Male', p, { x: 20, y: 120, width: 15, height: 15 });
g.addOptionToPage('Female', p, { x: 60, y: 120, width: 15, height: 15 });
await fs.writeFile(process.argv[2], await d.save());
"""

VERIFY_FILLED_JS = """
import { PDFDocument } from 'pdf-lib';
import * as fs from 'node:fs/promises';
const pdf = await PDFDocument.load(await fs.readFile(process.argv[2]));
const form = pdf.getForm();
console.log(form.getTextField('last_name').getText());
console.log(form.getRadioGroup('gender_group').getSelected());
"""


def example_tests():
    section("examples")

    scripts = extract_scripts()
    check("examples: scripts extracted", len(scripts) >= 10,
          f"only {len(scripts)} found")

    try:
        import pymupdf  # noqa: F401
    except ImportError:
        skip("examples: pymupdf block", "pip3 install pymupdf")
        return

    with tempfile.TemporaryDirectory(prefix="pdf-tools-examples-") as td:
        tdp = Path(td)
        make_fixtures(tdp)
        for name, (lang, code) in scripts.items():
            if name.endswith(".py"):
                (tdp / name).write_text(code)

        # --- JS side: scratch npm project with pdf-lib ---
        js_dir = tdp / "js"
        js_dir.mkdir()
        node = shutil.which("node")
        npm = shutil.which("npm")
        js_ok = False
        if node and npm:
            (js_dir / "package.json").write_text(
                '{"name":"pdf-tools-selftest","type":"module"}')
            for name, (lang, code) in scripts.items():
                if name.endswith(".js"):
                    (js_dir / name).write_text(code)
            (js_dir / "make-fillable.mjs").write_text(FILLABLE_FIXTURE_JS)
            (js_dir / "verify-filled.mjs").write_text(VERIFY_FILLED_JS)
            proc = subprocess.run(
                [npm, "i", "pdf-lib", "--silent", "--no-audit",
                 "--no-fund", "--prefer-offline"],
                cwd=js_dir, capture_output=True, text=True, timeout=180)
            js_ok = proc.returncode == 0
            if not js_ok:
                skip("examples: pdf-lib scripts", "npm install failed (offline?)")
        else:
            skip("examples: pdf-lib scripts", "node/npm not on PATH")

        def run_js(name, *args, cwd=js_dir):
            return subprocess.run([node, name, *args], cwd=cwd,
                                  capture_output=True, text=True, timeout=60)

        def run_py(name, *args):
            return subprocess.run(
                [sys.executable, str(tdp / name), *[str(a) for a in args]],
                cwd=tdp, capture_output=True, text=True, timeout=60)

        def py_pages(path):
            import pymupdf
            f = tdp / path
            return pymupdf.open(f) if f.exists() else None

        if js_ok:
            # fixture: fillable.pdf
            r = run_js("make-fillable.mjs", tdp / "fillable.pdf")
            check("js: fillable fixture built",
                  r.returncode == 0 and (tdp / "fillable.pdf").stat().st_size > 0,
                  r.stderr[:200])

            # inspect-form.js — expects FILLABLE + field dump
            r = run_js("inspect-form.js", tdp / "fillable.pdf")
            check("js: inspect-form.js reports FILLABLE + fields",
                  r.returncode == 0 and "FILLABLE" in r.stdout
                  and "gender_group" in r.stdout, r.stderr[:200])

            # fill-form.js — then verify values round-trip
            r = run_js("fill-form.js", tdp / "fillable.pdf",
                       tdp / "field_values.json", tdp / "filled-form.pdf")
            v = run_js("verify-filled.mjs", tdp / "filled-form.pdf") \
                if r.returncode == 0 else None
            check("js: fill-form.js fills text + radio",
                  v is not None and v.stdout.splitlines()[:2] == ["Simpson", "Male"],
                  f"{r.stderr[:150]} | {v.stdout if v else 'not run'}")

            # watermark.js — page count preserved
            if "watermark.js" in scripts:
                r = run_js("watermark.js", tdp / "input.pdf", tdp / "wm.pdf")
                ok = r.returncode == 0
                wm = py_pages("wm.pdf") if ok else None
                check("js: watermark.js keeps 3 pages",
                      wm is not None and len(wm) == 3, r.stderr[:200])

            # pages.js — delete + rotate
            if "pages.js" in scripts:
                r = run_js("pages.js", tdp / "input.pdf", tdp / "pages-out.pdf")
                ok = r.returncode == 0
                d = py_pages("pages-out.pdf") if ok else None
                check("js: pages.js removes page, rotates first",
                      d is not None and len(d) == 2 and d[0].rotation == 90,
                      r.stderr[:200])

            # add-image.js — embeds the 1px PNG
            if "add-image.js" in scripts:
                r = run_js("add-image.js", tdp / "input.pdf", tdp / "logo.png",
                           tdp / "img.pdf")
                ok = r.returncode == 0 and (tdp / "img.pdf").exists()
                check("js: add-image.js embeds PNG",
                      ok and (tdp / "img.pdf").read_bytes()[:5] == b"%PDF-",
                      r.stderr[:200])

        # --- Python side ---
        if "render_pages.py" in scripts:
            r = run_py("render_pages.py", tdp / "input.pdf", tdp / "rendered")
            pngs = sorted((tdp / "rendered").glob("page-*.png")) \
                if (tdp / "rendered").exists() else []
            check("py: render_pages.py writes one PNG per page",
                  r.returncode == 0 and len(pngs) == 3, r.stderr[:200])

        if "validate_boxes.py" in scripts:
            r = run_py("validate_boxes.py", tdp / "input.pdf",
                       tdp / "fields.json", tdp / "review.pdf")
            check("py: validate_boxes.py draws overlay",
                  r.returncode == 0 and (tdp / "review.pdf").exists(),
                  r.stderr[:200])

        if "fill_annotations.py" in scripts:
            r = run_py("fill_annotations.py", tdp / "input.pdf",
                       tdp / "fields.json", tdp / "filled-annot.pdf")
            text = py_pages("filled-annot.pdf")[0].get_text() \
                if r.returncode == 0 else ""
            check("py: fill_annotations.py writes entry text",
                  "Johnson" in text, r.stderr[:200])

        if "stamp.py" in scripts:
            r = run_py("stamp.py", tdp / "input.pdf", tdp / "stamp.pdf",
                       tdp / "py-stamped.pdf")
            d = py_pages("py-stamped.pdf") if r.returncode == 0 else None
            check("py: stamp.py stamps every page",
                  d is not None and all("APPROVED" in p.get_text() for p in d),
                  r.stderr[:200])

        if "redact.py" in scripts:
            r = run_py("redact.py", tdp / "secret.pdf", "SSN: 123-45-6789",
                       tdp / "redacted.pdf")
            red = py_pages("redacted.pdf") if r.returncode == 0 else None
            text = red[0].get_text() if red else "SSN still here"
            check("py: redact.py removes the target text",
                  r.returncode == 0 and red is not None
                  and "123-45-6789" not in text, r.stderr[:200])

        if "outline.py" in scripts:
            r = run_py("outline.py", tdp / "input.pdf", tdp / "outlined.pdf")
            outlined = py_pages("outlined.pdf") if r.returncode == 0 else None
            check("py: outline.py writes 3 bookmarks",
                  outlined is not None and len(outlined.get_toc()) == 3,
                  r.stderr[:200])
        if "merge.py" in scripts:
            r = run_py("merge.py", tdp / "merged.pdf", tdp / "input.pdf",
                       tdp / "input.pdf")
            merged = py_pages("merged.pdf") if r.returncode == 0 else None
            check("py: merge.py concatenates pages",
                  merged is not None and len(merged) == 6, r.stderr[:200])

        # --- ghostscript compression (skip if absent) ---
        gs = shutil.which("gs")
        if gs:
            r = subprocess.run(
                [gs, "-sDEVICE=pdfwrite", "-dPDFSETTINGS=/ebook", "-dNOPAUSE",
                 "-dQUIET", "-dBATCH", f"-sOutputFile={tdp/'compressed.pdf'}",
                 str(tdp / "input.pdf")],
                capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0 and (tdp / "compressed.pdf").exists()
            check("cli: gs compression produces a PDF", ok, r.stderr[:200])
        else:
            skip("cli: gs compression", "ghostscript not installed")


def main():
    structure_tests()
    drift_tests()
    prereq_block_tests()
    example_tests()
    total = PASSED[0] + FAILED[0]
    print(f"\n{'=' * 50}\n{PASSED[0]}/{total} passed, {FAILED[0]} failed, "
          f"{SKIPPED[0]} skipped")
    sys.exit(1 if FAILED[0] else 0)


if __name__ == "__main__":
    main()
