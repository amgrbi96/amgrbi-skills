#!/usr/bin/env python3
"""
PyMuPDF local PDF parser — PDF → Markdown/JSON (+ optional images/tables).

Design goals (fast local alternative to cloud parsers):
- Pre-flight checks: file existence, extension, size, valid unencrypted PDF
- --dry-run: validate the input and exit without writing anything
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


def has_pymupdf4llm() -> bool:
    try:
        import pymupdf4llm  # noqa: F401
        return True
    except ImportError:
        return False


def extract_markdown_4llm(doc) -> str:
    import pymupdf4llm  # lazy: keeps the basic engine dependency-free
    return pymupdf4llm.to_markdown(doc).strip() + "\n"


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


def extract_tables(doc) -> list:
    """Native table detection (page.find_tables, PyMuPDF >= 1.23).
    Falls back to line-based text per page on very old installs."""
    tables = []
    for i, page in enumerate(doc, start=1):
        if not hasattr(page, "find_tables"):  # PyMuPDF < 1.23
            tables.append({"page": i, "lines": page.get_text("text").splitlines()})
            continue
        finder = page.find_tables()
        for t_idx, tab in enumerate(finder.tables, start=1):
            tables.append({
                "page": i,
                "table": t_idx,
                "bbox": [round(v, 1) for v in tab.bbox],
                "row_count": tab.row_count,
                "col_count": tab.col_count,
                "rows": tab.extract(),
            })
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
    parser.add_argument("--md-engine", default="auto", choices=["auto", "basic", "pymupdf4llm"],
                        help="Markdown engine: auto uses pymupdf4llm when installed (headers, real tables), "
                             "else basic (default: auto)")
    parser.add_argument("--images", action="store_true", help="Extract images")
    parser.add_argument("--tables", action="store_true",
                        help="Extract tables via native page.find_tables() (rows as lists; "
                             "falls back to line-based output on PyMuPDF < 1.23)")
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

    # --- resolve markdown engine ---
    if args.md_engine == "pymupdf4llm" and not has_pymupdf4llm():
        print("❌ --md-engine pymupdf4llm requested but pymupdf4llm is not installed: "
              "pip install pymupdf4llm")
        doc.close()
        sys.exit(1)
    md_engine = args.md_engine
    if md_engine == "auto":
        md_engine = "pymupdf4llm" if has_pymupdf4llm() else "basic"
    print(f"⚙️  Markdown engine: {md_engine}")

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
            md_text = extract_markdown_4llm(doc) if md_engine == "pymupdf4llm" else extract_markdown(doc)
            md_path.write_text(md_text, encoding="utf-8")
            outputs.append(str(md_path))
            print(f"📝 {md_path} (engine: {md_engine})")

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
            tables = extract_tables(doc)
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
        'md_engine': md_engine if args.format in ("md", "both") else None,
        'status': 'ok',
        'outputs': outputs,
        'elapsed_sec': round(elapsed, 2),
    }, ensure_ascii=False)}")
    print(f"\n📁 Output: {outdir}")


if __name__ == "__main__":
    main()
