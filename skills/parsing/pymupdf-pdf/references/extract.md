# Text Extraction

Load when: pulling text out of a PDF in any form — plain, structured, positional, OCR, or search.

All examples assume `import pymupdf` and `doc = pymupdf.open("file.pdf")`.

## API map

| Need | Call |
|---|---|
| Plain text per page | `page.get_text("text")` |
| Markdown-ish text | `page.get_text("markdown")` |
| Positional dict (blocks/lines/spans with bboxes) | `page.get_text("dict")` |
| Words with bboxes | `page.get_text("words")` → list of `(x0, y0, x1, y1, word, block, line, word_no)` |
| HTML / XML | `page.get_text("html")` / `page.get_text("xml")` / `page.get_text("xhtml")` |
| Sorted reading order | `page.get_text("text", sort=True)` |
| Search | `page.search_for("query")` → list of `Rect` |
| OCR a scanned page | `tp = page.get_textpage_ocr(flags=0, full=True)` then `page.get_text(textpage=tp)` |
| High-quality Markdown | `pymupdf4llm.to_markdown(doc)` (separate package) |

## Whole-document text

```python
text = "\f".join(page.get_text() for page in doc)  # \f separates pages
```

## Words with positions (e.g. rebuilding layout, filtering by region)

```python
for w in page.get_text("words"):
    x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]
    if y0 < 200:          # top fifth of the page
        print(word)
```

## Spans with font info (detect headings by size)

```python
d = page.get_text("dict")
for block in d["blocks"]:
    for line in block.get("lines", []):
        for span in line["spans"]:
            if span["size"] > 14:
                print(f"heading? {span['text']!r} size={span['size']:.0f} font={span['font']}")
```

## Search and highlight

```python
for rect in page.search_for("important"):
    page.add_highlight_annot(rect)
doc.save("out.pdf")
```

## OCR (needs Tesseract installed — `brew install tesseract` / `apt install tesseract-ocr`)

```python
tp = page.get_textpage_ocr(flags=0, full=True)  # renders the page, OCRs it
print(page.get_text(textpage=tp))
```

## Gotchas

- `get_text()` reading order follows PDF internal order, not visual order — pass `sort=True` when layout fidelity matters.
- Scanned PDFs return empty strings without OCR; check `page.get_text().strip()` before assuming failure.
- OCR is 10–100× slower than native extraction; only reach for it when native text is empty.
- The CLI (`scripts/pymupdf_parse.py`) already covers md/json/engines/dry-run — use it before hand-rolling.
