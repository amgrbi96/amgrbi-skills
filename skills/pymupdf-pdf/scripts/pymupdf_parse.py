#!/usr/bin/env python3
"""
PyMuPDF local PDF parser — PDF → Markdown/JSON (+ optional images/tables).

Design goals (fast local alternative to cloud parsers):
- Pre-flight checks: file existence, extension, size, valid unencrypted PDF
- --dry-run: validate the input and exit without writing anything
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


def extract_markdown(doc) -> str:
    parts = []
    for i, page in enumerate(doc, start=1):
        try:
            text = page.get_text("markdown")
        except Exception:
            # Fallback for PyMuPDF versions without markdown support
            text = page.get_text("text")
        if text:
            parts.append(f"\n\n<!-- page {i} -->\n\n")
            parts.append(text)
    return "".join(parts).strip() + "\n"


def extract_json(doc, lang: str) -> dict:
    pages = []
    for i, page in enumerate(doc, start=1):
        pages.append({
            "page": i,
            "text": page.get_text("text"),
        })
    return {"lang": lang, "pages": pages}


def extract_images(doc, outdir: Path) -> int:
    count = 0
    for i, page in enumerate(doc, start=1):
        for img_index, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            pix = pymupdf.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3:  # CMYK: convert to RGB before saving
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(outdir / f"page-{i}-img-{img_index}.png")
            count += 1
    return count


def extract_tables_basic(doc) -> list:
    # PyMuPDF doesn't provide robust table extraction. This is a placeholder
    # returning line-based text per page for quick parsing.
    tables = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text")
        tables.append({"page": i, "lines": text.splitlines()})
    return tables


def main():
    parser = argparse.ArgumentParser(
        description="Parse a PDF locally with PyMuPDF into Markdown/JSON "
                    "(fast, less robust than OCR parsers)",
        epilog="Exit codes: 0 = success or dry-run OK, "
               "1 = invalid input, missing PyMuPDF, or parse failure.",
    )
    parser.add_argument("pdf", help="Path to PDF")
    parser.add_argument("--outroot", default="./pymupdf-output", help="Output root dir (default: ./pymupdf-output)")
    parser.add_argument("--format", default="md", choices=["md", "json", "both"], help="Output format (default: md)")
    parser.add_argument("--images", action="store_true", help="Extract images")
    parser.add_argument("--tables", action="store_true", help="Extract simple tables (lines)")
    parser.add_argument("--lang", default="en", help="Language hint recorded in JSON output (default: en)")
    parser.add_argument("--dry-run", action="store_true", help="Validate the input PDF, then exit without writing anything")
    args = parser.parse_args()

    if pymupdf is None:
        print(f"❌ PyMuPDF is required: pip install pymupdf ({NOTES_HINT})")
        sys.exit(1)

    # --- pre-flight checks ---
    pdf_path = Path(args.pdf)
    err = check_file(pdf_path)
    if err:
        print(f"🚫 {pdf_path}: {err}")
        sys.exit(1)

    doc, err = open_validated(pdf_path)
    if err:
        print(f"🚫 {pdf_path}: {err}")
        sys.exit(1)

    size_mb = pdf_path.stat().st_size / 1024 / 1024
    print(f"📄 {pdf_path.name} — {doc.page_count} pages, {size_mb:.1f} MB")

    if args.dry_run:
        print(f"✅ Dry run OK — valid PDF, {doc.page_count} pages. Ready to parse.")
        doc.close()
        return

    # --- extract ---
    outdir = Path(args.outroot) / pdf_path.stem
    outdir.mkdir(parents=True, exist_ok=True)
    outputs = []
    page_count = doc.page_count
    start = time.time()

    try:
        if args.format in ("md", "both"):
            md_path = outdir / "output.md"
            md_path.write_text(extract_markdown(doc), encoding="utf-8")
            outputs.append(str(md_path))
            print(f"📝 {md_path}")

        if args.format in ("json", "both"):
            data = extract_json(doc, args.lang)
            json_path = outdir / "output.json"
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs.append(str(json_path))
            print(f"🧾 {json_path}")

        if args.images:
            img_dir = outdir / "images"
            img_dir.mkdir(exist_ok=True)
            count = extract_images(doc, img_dir)
            outputs.append(str(img_dir))
            print(f"🖼️  {img_dir} ({count} image{'s' if count != 1 else ''})")

        if args.tables:
            tables = extract_tables_basic(doc)
            tables_path = outdir / "tables.json"
            tables_path.write_text(json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8")
            outputs.append(str(tables_path))
            print(f"📊 {tables_path}")
    except Exception as e:
        print(f"❌ Parse failed on page-level extraction: {e}")
        sys.exit(1)
    finally:
        doc.close()

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"📊 Summary (JSON):\n{json.dumps({
        'file': str(pdf_path),
        'pages': page_count,
        'status': 'ok',
        'outputs': outputs,
        'elapsed_sec': round(elapsed, 2),
    }, ensure_ascii=False)}")
    print(f"\n📁 Output: {outdir}")


if __name__ == "__main__":
    main()
