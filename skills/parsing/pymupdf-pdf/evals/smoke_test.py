#!/usr/bin/env python3
"""Self-contained smoke suite for the pymupdf-pdf skill.

Usage: python3 evals/smoke_test.py
Exits 0 only if every case passes. See evals/README.md.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
PARSE = SKILL / "scripts" / "pymupdf_parse.py"
OPS = SKILL / "scripts" / "pdf_ops.py"

passed = failed = 0


def check(name: str, ok: bool, detail: str = ""):
    global passed, failed
    passed += ok
    failed += not ok
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail and not ok else ""))


def run(script: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True)


def expect(name: str, r: subprocess.CompletedProcess, code: int = 0):
    check(name, r.returncode == code,
          f"exit {r.returncode} != {code}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")


# ---------- fixtures ----------
def build_fixtures(tmp: Path):
    import pymupdf

    # sample.pdf — 3 pages, text + one embedded image
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page()
        page.insert_text((72, 96), f"Test Document - Page {i}", fontsize=20)
        page.insert_text((72, 140), f"Paragraph {i}: the quick brown fox jumps over the lazy dog.", fontsize=11)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40))
    pix.set_rect(pix.irect, (255, 0, 0))
    doc[0].insert_image(pymupdf.Rect(400, 60, 460, 100), pixmap=pix)
    doc.save(tmp / "sample.pdf")

    # second.pdf — 2 pages
    doc = pymupdf.open()
    for label in ("Doc B alpha", "Doc B beta"):
        doc.new_page().insert_text((72, 96), label)
    doc.save(tmp / "second.pdf")

    # table.pdf — ruled 3x2 grid (header + 2 rows)
    doc = pymupdf.open()
    page = doc.new_page()
    x0, y0, cw, ch = 72, 100, 120, 28
    for r in range(4):
        page.draw_line((x0, y0 + r * ch), (x0 + 2 * cw, y0 + r * ch), width=0.7)
    for c in range(3):
        page.draw_line((x0 + c * cw, y0), (x0 + c * cw, y0 + 3 * ch), width=0.7)
    for r, row in enumerate([["name", "score"], ["alice", "90"], ["bob", "85"]]):
        for c, cell in enumerate(row):
            page.insert_text((x0 + c * cw + 6, y0 + r * ch + 19), cell, fontsize=10)
    doc.save(tmp / "table.pdf")

    (tmp / "corrupt.pdf").write_text("not a pdf")
    (tmp / "empty.pdf").write_bytes(b"")

    # encrypted.pdf
    doc = pymupdf.open(tmp / "sample.pdf")
    doc.save(tmp / "encrypted.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
             owner_pw="secret", user_pw="secret")
    return tmp


def cli_matrix(tmp: Path):
    print("\n--- pymupdf_parse.py ---")
    out = tmp / "parse-out"

    expect("single dry-run", run(PARSE, str(tmp / "sample.pdf"), "--outroot", str(out), "--dry-run"))
    r = run(PARSE, str(tmp / "sample.pdf"), "--outroot", str(out), "--format", "both", "--tables", "--images")
    expect("single full run", r)
    stem = out / "sample"
    check("outputs written", all((stem / n).exists() for n in
                                 ("output.md", "output.json", "tables.json")))
    check("md engine recorded", '"md_engine"' in r.stdout)

    tables = json.loads((stem / "tables.json").read_text())
    check("no tables in plain-text pdf", tables == [])  # sample.pdf has no ruled grid

    out_t = tmp / "table-out"
    expect("table fixture run", run(PARSE, str(tmp / "table.pdf"), "--outroot", str(out_t), "--tables"))
    tables = json.loads((out_t / "table" / "tables.json").read_text())
    check("native tables detected",
          len(tables) == 1 and tables[0]["rows"][0] == ["name", "score"], str(tables)[:120])

    r = run(PARSE, str(tmp / "sample.pdf"), "--outroot", str(out))
    expect("skip-if-exists rerun", r)
    check("rerun skipped", "⏭️" in r.stdout)

    out2 = tmp / "pages-out"
    expect("pages subset", run(PARSE, str(tmp / "sample.pdf"), "--outroot", str(out2),
                               "--format", "json", "--pages", "2-3"))
    pages = [p["page"] for p in json.loads((out2 / "sample" / "output.json").read_text())["pages"]]
    check("page numbers preserved", pages == [2, 3], str(pages))

    bdir = tmp / "batch"
    bdir.mkdir()
    for f in ("sample.pdf", "second.pdf", "table.pdf", "corrupt.pdf"):
        (bdir / f).write_bytes((tmp / f).read_bytes())
    r = run(PARSE, "--dir", str(bdir), "--outroot", str(tmp / "batch-out"), "--tables")
    expect("batch run (1 corrupt)", r)
    check("batch rejects corrupt", "🚫 corrupt.pdf" in r.stdout)

    expect("batch: no inputs", run(PARSE), 1)
    expect("batch: both inputs", run(PARSE, str(tmp / "sample.pdf"), "--dir", str(bdir)), 1)
    expect("err: missing file", run(PARSE, str(tmp / "nope.pdf")), 1)
    expect("err: empty file", run(PARSE, str(tmp / "empty.pdf")), 1)
    expect("err: non-pdf ext", run(PARSE, str(tmp / "corrupt.pdf").replace(".pdf", ".txt")), 1)
    expect("err: encrypted", run(PARSE, str(tmp / "encrypted.pdf")), 1)
    expect("err: page out of range", run(PARSE, str(tmp / "sample.pdf"), "--pages", "9"), 1)


def ops_matrix(tmp: Path):
    print("\n--- pdf_ops.py ---")
    o = tmp / "ops-out"
    o.mkdir()

    expect("info", run(OPS, "info", str(tmp / "sample.pdf")))
    expect("merge", run(OPS, "merge", "--inputs", str(tmp / "sample.pdf"),
                        str(tmp / "second.pdf"), "-o", str(o / "merged.pdf")))
    expect("merge dry", run(OPS, "merge", "--inputs", str(tmp / "sample.pdf"),
                            str(tmp / "second.pdf"), "-o", str(o / "m2.pdf"), "--dry-run"))
    expect("split ranged", run(OPS, "split", str(tmp / "sample.pdf"),
                               "--outroot", str(o / "split"), "--ranges", "1-2,3"))
    expect("rotate", run(OPS, "rotate", str(tmp / "sample.pdf"), "--pages", "1",
                         "--deg", "90", "-o", str(o / "rot.pdf")))
    expect("delete", run(OPS, "delete", str(tmp / "sample.pdf"), "--pages", "2",
                         "-o", str(o / "del.pdf")))
    expect("render", run(OPS, "render", str(tmp / "sample.pdf"), "--pages", "all",
                         "--dpi", "72", "--outroot", str(o / "png")))
    expect("meta read", run(OPS, "meta", str(tmp / "sample.pdf")))
    expect("meta set", run(OPS, "meta", str(tmp / "sample.pdf"), "--set", "title=T",
                           "-o", str(o / "meta.pdf")))
    toc_file = o / "toc.json"
    toc_file.write_text('[[1, "Intro", 1], [2, "Details", 2]]')
    expect("toc set", run(OPS, "toc", str(tmp / "sample.pdf"), "--json", str(toc_file),
                          "-o", str(o / "toc.pdf")))
    expect("toc read", run(OPS, "toc", str(o / "toc.pdf")))
    expect("search", run(OPS, "search", str(tmp / "sample.pdf"), "--text", "fox"))
    expect("encrypt", run(OPS, "encrypt", str(o / "meta.pdf"), "--user-pw", "pw", "-o", str(o / "enc.pdf")))
    expect("err: decrypt wrong pw", run(OPS, "decrypt", str(o / "enc.pdf"),
                                        "--password", "nope", "-o", str(o / "dec.pdf")), 1)
    expect("decrypt", run(OPS, "decrypt", str(o / "enc.pdf"), "--password", "pw",
                          "-o", str(o / "dec.pdf")))
    expect("err: missing input", run(OPS, "info", str(tmp / "nope.pdf")), 1)
    expect("err: bad range", run(OPS, "rotate", str(tmp / "sample.pdf"), "--pages", "9",
                                 "--deg", "90", "-o", str(o / "x.pdf")), 1)
    expect("err: same in/out", run(OPS, "rotate", str(tmp / "sample.pdf"), "--pages", "1",
                                   "--deg", "90", "-o", str(tmp / "sample.pdf")), 1)
    expect("err: encrypted no pw", run(OPS, "info", str(o / "enc.pdf")), 1)


def integrity(tmp: Path):
    print("\n--- output integrity ---")
    import pymupdf
    o = tmp / "ops-out"
    check("merged 5 pages", pymupdf.open(o / "merged.pdf").page_count == 5)
    d = pymupdf.open(o / "dec.pdf")
    check("decrypted opens", not d.needs_pass and d.page_count == 3)
    check("rotation applied", pymupdf.open(o / "rot.pdf")[0].rotation == 90)
    check("delete kept 2 pages", pymupdf.open(o / "del.pdf").page_count == 2)
    check("toc roundtrip", len(pymupdf.open(o / "toc.pdf").get_toc()) == 2)
    check("png rendered", (o / "png" / "sample-p2.png").exists())
    m = pymupdf.open(o / "meta.pdf")
    check("metadata applied", m.metadata["title"] == "T")


def reference_snippets(tmp: Path):
    print("\n--- reference snippets ---")
    import pymupdf

    # extract.md: words/dict/sort/search
    doc = pymupdf.open(tmp / "sample.pdf")
    words = doc[0].get_text("words")
    check("extract: words", bool(words) and words[0][4] == "Test")
    span = doc[0].get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
    check("extract: span size", span["size"] == 20)
    check("extract: search", bool(doc[0].search_for("fox")))

    # tables-images-layout.md: borderless tables are invisible to find_tables();
    # find their pages by caption regex instead and route them to mineru
    bdoc = pymupdf.open()
    bpage = bdoc.new_page()
    bpage.insert_text((72, 96), "Table 3.1  Dosing thresholds", fontsize=11)
    bpage.insert_text((72, 120), "drug      dose", fontsize=10)
    bpage.insert_text((72, 140), "lithium   600 mg", fontsize=10)
    bdoc.save(tmp / "borderless.pdf")
    check("tables: borderless invisible to find_tables",
          len(bdoc[0].find_tables().tables) == 0)
    caption_pages = [i + 1 for i in range(bdoc.page_count)
                     if re.search(r"Table \d+\.\d+", bdoc[i].get_text())]
    check("tables: caption regex finds borderless page",
          caption_pages == [1], str(caption_pages))

    # annotate-forms-redact.md: highlight + widget + redact
    d = pymupdf.open(tmp / "sample.pdf")
    for r in d[0].search_for("fox"):
        d[0].add_highlight_annot(r)
    check("annot: listed", len(list(d[0].annots())) >= 1)
    w = pymupdf.Widget()
    w.field_name, w.field_type = "email", pymupdf.PDF_WIDGET_TYPE_TEXT
    w.rect = pymupdf.Rect(100, 600, 400, 625)
    d[0].add_widget(w)
    d.save(tmp / "ref-annot.pdf")
    d2 = pymupdf.open(tmp / "ref-annot.pdf")
    check("forms: is_form_pdf", d2.is_form_pdf)
    page2 = d2[0]                      # keep the page alive: widget.update()
    wd = list(page2.widgets())[0]      # needs its annot bound to a Page
    wd.field_value = "x@y.z"
    wd.update()
    d2.save(tmp / "ref-filled.pdf")
    check("forms: fill persisted",
          next(pymupdf.open(tmp / "ref-filled.pdf")[0].widgets()).field_value == "x@y.z")
    d3 = pymupdf.open(tmp / "sample.pdf")
    for r in d3[0].search_for("fox"):
        d3[0].add_redact_annot(r)
    d3[0].apply_redactions()
    d3.save(tmp / "ref-redacted.pdf")
    check("redact: removed", not pymupdf.open(tmp / "ref-redacted.pdf")[0].search_for("fox"))

    # create.md: Story HTML->PDF
    story = pymupdf.Story(html="<h2>R</h2><p>styled</p>")
    writer = pymupdf.DocumentWriter(str(tmp / "ref-story.pdf"))
    mb = pymupdf.paper_rect("a4")
    more = 1
    while more:
        dev = writer.begin_page(mb)
        more, _ = story.place(mb + (36, 36, -36, -36))
        story.draw(dev)
        writer.end_page()
    writer.close()
    check("create: story text", "styled" in pymupdf.open(tmp / "ref-story.pdf")[0].get_text())

    # security-metadata.md: embfile + toc set
    d4 = pymupdf.open(tmp / "sample.pdf")
    d4.embfile_add("data.csv", b"a,b", filename="data.csv")
    d4.set_metadata({"title": "T"})
    d4.save(tmp / "ref-sec.pdf")
    d5 = pymupdf.open(tmp / "ref-sec.pdf")
    check("security: embfile roundtrip", d5.embfile_get("data.csv") == b"a,b")
    check("security: metadata", d5.metadata["title"] == "T")


def main():
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        print("❌ pymupdf not installed — run evals inside an environment that has it")
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="pymupdf-evals-") as td:
        tmp = build_fixtures(Path(td))
        cli_matrix(tmp)
        ops_matrix(tmp)
        integrity(tmp)
        reference_snippets(tmp)

    print(f"\n{'='*40}\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
