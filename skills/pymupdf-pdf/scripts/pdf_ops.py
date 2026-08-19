#!/usr/bin/env python3
"""
PyMuPDF PDF operations CLI — merge, split, rotate, render, meta, TOC,
search, encrypt/decrypt. Companion to pymupdf_parse.py (extraction).

Conventions (same as pymupdf_parse.py):
- Pre-flight checks: file existence, extension, valid PDF, password where needed
- --dry-run on every subcommand: validate inputs, write nothing
- Exit codes: 0 = success (or dry-run OK), 1 = bad input / missing dep / failure
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

NOTES_HINT = "see references/pymupdf-notes.md in this skill (install + Nix libstdc++ help)"

META_KEYS = {"title", "author", "subject", "keywords", "creator", "producer",
             "creationDate", "modDate"}


def check_file(f: Path, what: str = "input") -> str | None:
    """Return an error string if the file can't be used, else None."""
    if not f.exists():
        return f"{what} not found"
    if not f.is_file():
        return f"{what} is not a regular file"
    if f.suffix.lower() != ".pdf":
        return f"{what} is not a PDF (got '{f.suffix or 'none'}')"
    if f.stat().st_size == 0:
        return f"{what} is empty"
    return None


def open_or_exit(path: str, password: str | None = None):
    """Pre-flight + open a PDF; exit 1 with a clear message on any problem."""
    f = Path(path)
    err = check_file(f)
    if err:
        print(f"🚫 {f}: {err}")
        sys.exit(1)
    try:
        doc = pymupdf.open(f)
    except pymupdf.FileDataError:
        print(f"🚫 {f}: not a valid PDF (corrupt or wrong format)")
        sys.exit(1)
    except Exception as e:
        print(f"🚫 {f}: cannot open: {e}")
        sys.exit(1)
    if doc.needs_pass and (not password or not doc.authenticate(password)):
        doc.close()
        print(f"🚫 {f}: password-protected PDF — supply the correct --password")
        sys.exit(1)
    return doc


def parse_pages(spec: str, page_count: int) -> list[int]:
    """Parse '1-3,5' or 'all' (1-indexed, inclusive) into sorted 0-indexed pages."""
    if spec.strip().lower() == "all":
        return list(range(page_count))
    picked = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                lo_i, hi_i = int(lo), int(hi)
            except ValueError:
                raise SystemExit(f"🚫 bad page range '{part}' (expected e.g. 1-3,5)")
            if lo_i < 1 or hi_i < lo_i or hi_i > page_count:
                raise SystemExit(f"🚫 page range '{part}' outside 1..{page_count}")
            picked.update(range(lo_i - 1, hi_i))
        else:
            try:
                n = int(part)
            except ValueError:
                raise SystemExit(f"🚫 bad page number '{part}' (expected e.g. 1-3,5)")
            if n < 1 or n > page_count:
                raise SystemExit(f"🚫 page number {n} outside 1..{page_count}")
            picked.add(n - 1)
    if not picked:
        raise SystemExit("🚫 empty page selection")
    return sorted(picked)


def save_doc(doc, out: Path, src: Path | None = None, **kw):
    if src is not None and out.resolve() == src.resolve():
        print(f"🚫 output must differ from input ({out}) — in-place edits are not supported")
        sys.exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # save() refuses to overwrite
    doc.save(out, garbage=3, deflate=True, **kw)


def summary(op: str, out: Path | None, pages, start: float, extra: dict | None = None):
    payload = {"op": op, "status": "ok", "elapsed_sec": round(time.time() - start, 2)}
    if out is not None:
        payload["output"] = str(out)
    if pages is not None:
        payload["pages"] = pages
    if extra:
        payload.update(extra)
    print(f"\n{'='*50}")
    print(f"📊 Summary (JSON):\n{json.dumps(payload, ensure_ascii=False)}")


def op_info(args, start):
    doc = open_or_exit(args.pdf, args.password)
    info = {
        "file": args.pdf,
        "pages": doc.page_count,
        "encrypted": doc.is_encrypted,
        "metadata": doc.metadata,
        "toc_entries": len(doc.get_toc()),
        "size_kb": round(Path(args.pdf).stat().st_size / 1024, 1),
    }
    doc.close()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    summary("info", None, info["pages"], start)


def op_merge(args, start):
    inputs = [Path(p) for p in args.inputs]
    if len(inputs) < 2:
        print("🚫 merge needs at least 2 --inputs")
        sys.exit(1)
    for f in inputs:
        err = check_file(f)
        if err:
            print(f"🚫 {f}: {err}")
            sys.exit(1)
    out = Path(args.output)
    docs, total = [], 0
    try:
        for f in inputs:
            doc = open_or_exit(f, args.password)
            docs.append(doc)
            total += doc.page_count
        print(f"🔗 merge: {len(docs)} file(s), {total} page(s) -> {out}")
        if args.dry_run:
            print(f"✅ Dry run OK — merge ready ({len(docs)} file(s), {total} pages).")
            return
        merged = pymupdf.open()
        for doc in docs:
            merged.insert_pdf(doc)
        save_doc(merged, out)
        merged.close()
        print(f"✅ Merged into {out}")
        summary("merge", out, total, start)
    finally:
        for doc in docs:
            if not doc.is_closed:
                doc.close()


def op_split(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    n = doc.page_count
    outroot = Path(args.outroot)
    stem = src.stem

    if args.ranges:  # grouped: "1-3,4-6" -> one PDF per range
        groups = []
        for part in args.ranges.split(","):
            pages = parse_pages(part, n)
            groups.append((pages[0], pages[-1], f"{stem}-{pages[0]+1}-{pages[-1]+1}.pdf"))
    else:  # default: one PDF per page
        groups = [(i, i, f"{stem}-p{i+1}.pdf") for i in range(n)]

    print(f"✂️  split: {src.name} ({n} pages) -> {len(groups)} file(s) in {outroot}")
    if args.dry_run:
        print(f"✅ Dry run OK — would write {len(groups)} file(s).")
        doc.close()
        return
    written = []
    for lo, hi, name in groups:
        part = pymupdf.open()
        part.insert_pdf(doc, from_page=lo, to_page=hi)
        out = outroot / name
        save_doc(part, out)
        part.close()
        written.append(str(out))
        print(f"📄 {out}")
    doc.close()
    summary("split", outroot, written, start)


def op_rotate(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    pages = parse_pages(args.pages, doc.page_count)
    print(f"🔄 rotate {args.deg}° on page(s) {args.pages} -> {args.output}")
    if args.dry_run:
        print(f"✅ Dry run OK — would rotate {len(pages)} page(s).")
        doc.close()
        return
    for p in pages:
        doc[p].set_rotation(args.deg)
    out = Path(args.output)
    save_doc(doc, out, src=src)
    doc.close()
    print(f"✅ Rotated -> {out}")
    summary("rotate", out, len(pages), start)


def op_delete(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    n = doc.page_count
    keep = [i for i in range(n) if i not in set(parse_pages(args.pages, n))]
    if not keep:
        print("🚫 refusing to delete every page")
        sys.exit(1)
    print(f"🗑️  delete page(s) {args.pages}: {n} -> {len(keep)} pages -> {args.output}")
    if args.dry_run:
        print(f"✅ Dry run OK — would keep {len(keep)} page(s).")
        doc.close()
        return
    doc.select(keep)
    out = Path(args.output)
    save_doc(doc, out, src=src)
    kept = doc.page_count
    doc.close()
    print(f"✅ {out} ({kept} pages)")
    summary("delete", out, kept, start)


def op_render(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    pages = parse_pages(args.pages, doc.page_count)
    outroot = Path(args.outroot)
    print(f"🖼️  render page(s) {args.pages} at {args.dpi} DPI -> {outroot}")
    if args.dry_run:
        print(f"✅ Dry run OK — would render {len(pages)} PNG(s).")
        doc.close()
        return
    outroot.mkdir(parents=True, exist_ok=True)
    written = []
    for p in pages:
        pix = doc[p].get_pixmap(dpi=args.dpi)
        out = outroot / f"{src.stem}-p{p+1}.png"
        pix.save(out)
        written.append(str(out))
        print(f"🖼️  {out}")
    doc.close()
    summary("render", outroot, written, start)


def op_meta(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    if not args.set:
        print(json.dumps(doc.metadata, ensure_ascii=False, indent=2))
        doc.close()
        summary("meta", None, None, start, extra={"mode": "read"})
        return
    updates = {}
    for kv in args.set:
        key, sep, val = kv.partition("=")
        if not sep:
            print(f"🚫 bad --set '{kv}' (expected key=value)")
            sys.exit(1)
        if key not in META_KEYS:
            print(f"🚫 unknown metadata key '{key}' (valid: {', '.join(sorted(META_KEYS))})")
            sys.exit(1)
        updates[key] = val
    print(f"🏷️  set metadata {updates} -> {args.output}")
    if args.dry_run:
        print("✅ Dry run OK — metadata update ready.")
        doc.close()
        return
    doc.set_metadata(updates)
    out = Path(args.output)
    save_doc(doc, out, src=src)
    doc.close()
    print(f"✅ Metadata written -> {out}")
    summary("meta", out, None, start, extra={"updated": sorted(updates)})


def op_toc(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    if not args.json:
        toc = doc.get_toc()
        print(json.dumps(toc, ensure_ascii=False, indent=2))
        doc.close()
        summary("toc", None, len(toc), start, extra={"mode": "read"})
        return
    try:
        toc = json.loads(Path(args.json).read_text())
        for entry in toc:
            if not (isinstance(entry, list) and len(entry) == 3):
                raise ValueError(f"entry {entry} is not [level, title, page]")
            if not (1 <= entry[0] <= 6) or not (1 <= entry[2] <= doc.page_count):
                raise ValueError(f"entry {entry}: level must be 1..6, page 1..{doc.page_count}")
    except (OSError, ValueError) as e:
        print(f"🚫 bad TOC file {args.json}: {e}")
        sys.exit(1)
    print(f"📚 set {len(toc)} TOC entries -> {args.output}")
    if args.dry_run:
        print("✅ Dry run OK — TOC update ready.")
        doc.close()
        return
    doc.set_toc(toc)
    out = Path(args.output)
    save_doc(doc, out, src=src)
    doc.close()
    print(f"✅ TOC written -> {out}")
    summary("toc", out, len(toc), start)


def op_search(args, start):
    doc = open_or_exit(args.pdf, args.password)
    hits = {}
    for i, page in enumerate(doc, start=1):
        rects = page.search_for(args.text)
        if rects:
            hits[str(i)] = [[round(v, 1) for v in r] for r in rects]
    doc.close()
    total = sum(len(v) for v in hits.values())
    print(json.dumps({"query": args.text, "total_hits": total, "pages": hits},
                     ensure_ascii=False, indent=2))
    summary("search", None, total, start)


def op_encrypt(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    print(f"🔒 encrypt {src.name} (AES-256) -> {args.output}")
    if args.dry_run:
        print("✅ Dry run OK — encryption ready.")
        doc.close()
        return
    out = Path(args.output)
    save_doc(doc, out, src=src,
             encryption=pymupdf.PDF_ENCRYPT_AES_256,
             user_pw=args.user_pw,
             owner_pw=args.owner_pw or args.user_pw)
    doc.close()
    print(f"✅ Encrypted -> {out}")
    summary("encrypt", out, None, start)


def op_decrypt(args, start):
    src = Path(args.pdf)
    doc = open_or_exit(args.pdf, args.password)
    print(f"🔓 decrypt {src.name} -> {args.output}")
    if args.dry_run:
        print("✅ Dry run OK — decryption ready (password verified).")
        doc.close()
        return
    out = Path(args.output)
    save_doc(doc, out, src=src, encryption=pymupdf.PDF_ENCRYPT_NONE)
    doc.close()
    print(f"✅ Decrypted -> {out}")
    summary("decrypt", out, None, start)


def main():
    # flags shared by every subcommand (argparse only accepts subparser
    # options AFTER the subcommand name, so these live on the parent)
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--dry-run", action="store_true",
                        help="Validate inputs, write nothing")
    parent.add_argument("--password", help="Password for opening encrypted input PDFs")

    parser = argparse.ArgumentParser(
        description="PDF operations with PyMuPDF: merge, split, rotate, render, "
                    "metadata, TOC, search, encrypt/decrypt. Subcommand flags "
                    "(including --dry-run/--password) go AFTER the subcommand name. "
                    "Exit codes: 0 = success or dry-run OK, 1 = failure.",
    )
    sub = parser.add_subparsers(dest="op", required=True)

    p = sub.add_parser("info", parents=[parent], help="Report pages, metadata, TOC size, encryption state")
    p.add_argument("pdf")
    p.set_defaults(fn=op_info)

    p = sub.add_parser("merge", parents=[parent], help="Concatenate PDFs")
    p.add_argument("--inputs", nargs="+", required=True, help="Two or more PDF paths")
    p.add_argument("--output", "-o", required=True)
    p.set_defaults(fn=op_merge)

    p = sub.add_parser("split", parents=[parent], help="Split into per-page PDFs, or grouped by --ranges")
    p.add_argument("pdf")
    p.add_argument("--outroot", default="./pdf-ops-output", help="Output dir (default: ./pdf-ops-output)")
    p.add_argument("--ranges", help="Grouped ranges, e.g. '1-3,4-6' (default: one PDF per page)")
    p.set_defaults(fn=op_split)

    p = sub.add_parser("rotate", parents=[parent], help="Rotate pages (90/180/270)")
    p.add_argument("pdf")
    p.add_argument("--pages", required=True, help="Pages, e.g. '1-3,5' or 'all'")
    p.add_argument("--deg", type=int, required=True, choices=[90, 180, 270])
    p.add_argument("--output", "-o", required=True)
    p.set_defaults(fn=op_rotate)

    p = sub.add_parser("delete", parents=[parent], help="Delete pages; writes result to --output")
    p.add_argument("pdf")
    p.add_argument("--pages", required=True, help="Pages to delete, e.g. '2,5-7'")
    p.add_argument("--output", "-o", required=True)
    p.set_defaults(fn=op_delete)

    p = sub.add_parser("render", parents=[parent], help="Render pages to PNG")
    p.add_argument("pdf")
    p.add_argument("--pages", required=True, help="Pages, e.g. '1-3,5' or 'all'")
    p.add_argument("--dpi", type=int, default=150, help="Resolution (default: 150)")
    p.add_argument("--outroot", default="./pdf-ops-output")
    p.set_defaults(fn=op_render)

    p = sub.add_parser("meta", parents=[parent], help="Read (default) or update document metadata")
    p.add_argument("pdf")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help=f"Set metadata; repeatable. Keys: {', '.join(sorted(META_KEYS))}")
    p.add_argument("--output", "-o", help="Required with --set")
    p.set_defaults(fn=op_meta)

    p = sub.add_parser("toc", parents=[parent], help="Read (default) or set the table of contents")
    p.add_argument("pdf")
    p.add_argument("--json", help="TOC file: JSON list of [level, title, page]")
    p.add_argument("--output", "-o", help="Required with --json")
    p.set_defaults(fn=op_toc)

    p = sub.add_parser("search", parents=[parent], help="Find text; prints JSON of hit rects per page")
    p.add_argument("pdf")
    p.add_argument("--text", required=True)
    p.set_defaults(fn=op_search)

    p = sub.add_parser("encrypt", parents=[parent], help="Encrypt with AES-256")
    p.add_argument("pdf")
    p.add_argument("--user-pw", required=True)
    p.add_argument("--owner-pw", help="Default: same as --user-pw")
    p.add_argument("--output", "-o", required=True)
    p.set_defaults(fn=op_encrypt)

    p = sub.add_parser("decrypt", parents=[parent], help="Decrypt (needs --password) and strip encryption")
    p.add_argument("pdf")
    p.add_argument("--output", "-o", required=True)
    p.set_defaults(fn=op_decrypt)

    args = parser.parse_args()

    if pymupdf is None:
        print(f"❌ PyMuPDF is required: pip install pymupdf ({NOTES_HINT})")
        sys.exit(1)

    if getattr(args, "set", None) and not getattr(args, "output", None):
        print("🚫 --set requires --output")
        sys.exit(1)
    if getattr(args, "json", None) and not getattr(args, "output", None):
        print("🚫 --json requires --output")
        sys.exit(1)

    args.fn(args, time.time())


if __name__ == "__main__":
    main()
