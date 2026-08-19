#!/usr/bin/env python3
"""
PyMuPDF local PDF parser — PDF → Markdown/JSON (+ optional images/tables).

Design goals (fast local alternative to cloud parsers):
- Single PDF or batch directory (--dir), skipping already-parsed documents
- Pre-flight checks: file existence, extension, size, valid unencrypted PDF
- --dry-run: validate everything and exit without writing anything
- Markdown engine choice: basic (get_text) or pymupdf4llm (headers, real
  tables, auto; falls back to basic if the extra package is absent)
- Clear error when PyMuPDF is missing — no stack trace
- Exit codes: 0 = success (or dry-run OK), 1 = bad input / missing dep / parse failure
- JSON summary at the end for machine consumption
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import pymupdf  # canonical import since PyMuPDF 1.24
except ImportError:
    try:
        import fitz as pymupdf  # older versions only exposed the fitz name
    except ImportError:
        pymupdf = None  # checked in main; lets --help work without the dep

from pdf_ops import parse_pages  # sibling script, same directory

SUPPORTED_EXTS = {".pdf"}
NOTES_HINT = "see references/pymupdf-notes.md in this skill (install + Nix libstdc++ help)"


def check_file(f: Path) -> str | None:
    """Return an error string if the file can't be parsed, else None."""
    if not f.exists():
        return "file not found"
    if not f.is_file():
        return "not a regular file"
    if f.suffix.lower() not in SUPPORTED_EXTS:
        return f"unsupported type '{f.suffix or 'none'}' (supported: {', '.join(sorted(SUPPORTED_EXTS))})"
    if f.stat().st_size == 0:
        return "empty file"
    return None


def open_validated(path: Path):
    """Open the PDF with pre-flight validation. Returns (doc, error_message)."""
    try:
        doc = pymupdf.open(path)
    except pymupdf.FileDataError:
        return None, "not a valid PDF (corrupt or wrong format)"
    except Exception as e:
        return None, f"cannot open: {e}"
    if doc.needs_pass:
        doc.close()
        return None, "password-protected PDF — remove the password first"
    return doc, None


def page_indices(doc, pages_spec: str | None) -> list[int]:
    """Resolve --pages ('1-3,5') to sorted 0-indexed indices; all pages if None."""
    if not pages_spec:
        return list(range(doc.page_count))
    return parse_pages(pages_spec, doc.page_count)


def extract_markdown(doc, indices: list[int]) -> str:
    parts = []
    for i in indices:
        try:
            text = doc[i].get_text("markdown")
        except Exception:
            # Fallback for PyMuPDF versions without markdown support
            text = doc[i].get_text("text")
        if text:
            parts.append(f"\n\n<!-- page {i + 1} -->\n\n")
            parts.append(text)
    return "".join(parts).strip() + "\n"


def extract_json(doc, lang: str, indices: list[int]) -> dict:
    pages = []
    for i in indices:
        pages.append({
            "page": i + 1,
            "text": doc[i].get_text("text"),
        })
    return {"lang": lang, "pages": pages}


def extract_images(doc, outdir: Path, indices: list[int]) -> int:
    count = 0
    for i in indices:
        for img_index, img in enumerate(doc[i].get_images(full=True), start=1):
            xref = img[0]
            pix = pymupdf.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3:  # CMYK: convert to RGB before saving
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(outdir / f"page-{i + 1}-img-{img_index}.png")
            count += 1
    return count


def extract_tables(doc, indices: list[int]) -> list:
    """Native table detection (page.find_tables, PyMuPDF >= 1.23).
    Falls back to line-based text per page on very old installs."""
    tables = []
    for i in indices:
        page = doc[i]
        if not hasattr(page, "find_tables"):  # PyMuPDF < 1.23
            tables.append({"page": i + 1, "lines": page.get_text("text").splitlines()})
            continue
        finder = page.find_tables()
        for t_idx, tab in enumerate(finder.tables, start=1):
            tables.append({
                "page": i + 1,
                "table": t_idx,
                "bbox": [round(v, 1) for v in tab.bbox],
                "row_count": tab.row_count,
                "col_count": tab.col_count,
                "rows": tab.extract(),
            })
    return tables


def has_pymupdf4llm() -> bool:
    try:
        import pymupdf4llm  # noqa: F401
        return True
    except ImportError:
        return False


def extract_markdown_4llm(doc) -> str:
    import pymupdf4llm  # lazy: keeps the basic engine dependency-free
    return pymupdf4llm.to_markdown(doc).strip() + "\n"


def process_one(pdf_path: Path, outroot: Path, args, md_engine: str):
    """Parse one validated file. Returns (status, result_summary_dict)."""
    stem = pdf_path.stem
    outdir = outroot / stem
    if outdir.exists():
        print(f"  ⏭️  {stem} (output exists: {outdir})")
        return "skipped", {"file": str(pdf_path), "status": "skipped"}

    doc, err = open_validated(pdf_path)
    if err:
        print(f"  ❌ {stem}: {err}")
        return "failed", {"file": str(pdf_path), "status": "failed", "error": err}

    indices = page_indices(doc, args.pages)
    outdir.mkdir(parents=True, exist_ok=True)
    outputs, page_count = [], doc.page_count
    print(f"  📤 {stem} ({page_count} pages, {len(indices)} selected)")

    try:
        if args.format in ("md", "both"):
            md_path = outdir / "output.md"
            md_text = extract_markdown_4llm(doc) if md_engine == "pymupdf4llm" else extract_markdown(doc, indices)
            md_path.write_text(md_text, encoding="utf-8")
            outputs.append(str(md_path))
            print(f"     📝 {md_path} (engine: {md_engine})")

        if args.format in ("json", "both"):
            data = extract_json(doc, args.lang, indices)
            json_path = outdir / "output.json"
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs.append(str(json_path))
            print(f"     🧾 {json_path}")

        if args.images:
            img_dir = outdir / "images"
            img_dir.mkdir(exist_ok=True)
            count = extract_images(doc, img_dir, indices)
            outputs.append(str(img_dir))
            print(f"     🖼️  {img_dir} ({count} image{'s' if count != 1 else ''})")

        if args.tables:
            tables = extract_tables(doc, indices)
            tables_path = outdir / "tables.json"
            tables_path.write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs.append(str(tables_path))
            print(f"     📊 {tables_path} ({len(tables)} table{'s' if len(tables) != 1 else ''})")
    except Exception as e:
        print(f"  ❌ {stem}: parse failed: {e}")
        return "failed", {"file": str(pdf_path), "status": "failed", "error": str(e)}
    finally:
        doc.close()

    result = {"file": str(pdf_path), "pages": page_count, "status": "ok", "outputs": outputs}
    if args.pages:
        result["pages_selected"] = len(indices)
    if args.format in ("md", "both"):
        result["md_engine"] = md_engine
    return "ok", result


def main():
    parser = argparse.ArgumentParser(
        description="Parse PDFs locally with PyMuPDF into Markdown/JSON "
                    "(fast, less robust than OCR parsers)",
        epilog="Exit codes: 0 = success or dry-run OK, "
               "1 = invalid input, missing PyMuPDF, or parse failure.",
    )
    parser.add_argument("pdf", nargs="?", help="Path to a single PDF (or use --dir)")
    parser.add_argument("--dir", dest="dir", help="Batch: parse every PDF in this directory")
    parser.add_argument("--pages", help="Page ranges, e.g. '1-3,5' (default: all; applies to every file in batch mode)")
    parser.add_argument("--outroot", default="./pymupdf-output", help="Output root dir (default: ./pymupdf-output)")
    parser.add_argument("--format", default="md", choices=["md", "json", "both"], help="Output format (default: md)")
    parser.add_argument("--md-engine", default="auto", choices=["auto", "basic", "pymupdf4llm"],
                        help="Markdown engine: auto uses pymupdf4llm when installed (headers, real tables), "
                             "else basic (default: auto)")
    parser.add_argument("--images", action="store_true", help="Extract images")
    parser.add_argument("--tables", action="store_true",
                        help="Extract tables via native page.find_tables() (rows as lists; "
                             "falls back to line-based output on PyMuPDF < 1.23)")
    parser.add_argument("--lang", default="en", help="Language hint recorded in JSON output (default: en)")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs, then exit without writing anything")
    args = parser.parse_args()

    if pymupdf is None:
        print(f"❌ PyMuPDF is required: pip install pymupdf>=1.23 ({NOTES_HINT})")
        sys.exit(1)

    if bool(args.pdf) == bool(args.dir):
        print("🚫 provide exactly one input: either a PDF path or --dir DIR")
        sys.exit(1)

    # --- collect and pre-flight files ---
    if args.pdf:
        raw_files = [Path(args.pdf)]
    else:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"🚫 {d}: not a directory")
            sys.exit(1)
        raw_files = sorted(d.glob("*.pdf"))
        if not raw_files:
            print(f"🚫 {d}: no PDF files found")
            sys.exit(1)

    input_files, rejected = [], []
    for f in raw_files:
        err = check_file(f)
        (input_files if err is None else rejected).append((f, err))
    for f, err in rejected:
        print(f"🚫 {f.name}: {err}")

    # open-validate each (corrupt/encrypted/… rejected here, not mid-run)
    validated = []
    for f, _ in input_files:
        doc, err = open_validated(f)
        if err:
            print(f"🚫 {f.name}: {err}")
            continue
        validated.append((f, doc.page_count, page_indices(doc, args.pages)))
        doc.close()
    if not validated:
        print("❌ No valid PDFs to parse")
        sys.exit(1)

    # --- resolve markdown engine ---
    if args.md_engine == "pymupdf4llm" and not has_pymupdf4llm():
        print("❌ --md-engine pymupdf4llm requested but pymupdf4llm is not installed: "
              "pip install pymupdf4llm")
        sys.exit(1)
    md_engine = args.md_engine
    if md_engine == "auto":
        md_engine = "pymupdf4llm" if has_pymupdf4llm() else "basic"

    total_pages = sum(n for _, n, _ in validated)
    total_selected = sum(len(ix) for _, _, ix in validated)
    print(f"\n📚 {len(validated)} PDF(s), {total_pages} pages"
          + (f", {total_selected} selected" if args.pages else "")
          + f" | format: {args.format} | engine: {md_engine}")

    if args.dry_run:
        outroot = Path(args.outroot)
        would_skip = sum(1 for f, _, _ in validated if (outroot / f.stem).exists())
        print(f"✅ Dry run OK — {len(validated)} valid PDF(s), "
              f"{would_skip} already parsed (would skip). Ready.")
        return

    # --- process ---
    start = time.time()
    outroot = Path(args.outroot)
    outroot.mkdir(parents=True, exist_ok=True)
    results = {"ok": [], "skipped": [], "failed": []}
    for f, _, _ in validated:
        status, res = process_one(f, outroot, args, md_engine)
        results[status].append(res)

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"✅ Parsed: {len(results['ok'])}  ⏭️  Skipped: {len(results['skipped'])}  "
          f"❌ Failed: {len(results['failed'])}")
    summary = {
        "files": len(validated),
        "parsed": results["ok"],
        "skipped": [s["file"] for s in results["skipped"]],
        "failed": results["failed"],
        "output": str(outroot),
        "elapsed_sec": round(elapsed, 2),
    }
    print(f"📊 Summary (JSON):\n{json.dumps(summary, ensure_ascii=False)}")
    sys.exit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
