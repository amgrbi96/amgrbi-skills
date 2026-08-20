# Tables, Images, Rendering, Layout Detection

Load when: extracting tables or embedded images, rendering pages/clips to PNG, or doing block-level layout detection.

All examples assume `import pymupdf` and `doc = pymupdf.open("file.pdf")`.

## Tables — `page.find_tables()` (PyMuPDF ≥ 1.23)

```python
tabs = page.find_tables()          # TableFinder
for tab in tabs.tables:
    print(tab.bbox)                # (x0, y0, x1, y1)
    print(tab.row_count, tab.col_count)
    for row in tab.extract():      # list of lists; None for empty cells
        print(row)
```

- Detects **ruled tables by vector lines** (best), and borderless tables with `strategy="text"` (positional heuristic — weak on real borderless tables; see below).
- CLI: `scripts/pymupdf_parse.py file.pdf --tables` writes `tables.json` with bbox + rows.

### Borderless-table blindness — check before trusting a "no tables" result

`find_tables()` is effectively **ruled-table-only** on real books: `strategy="text"` rarely recovers academic/clinical borderless tables. Field check (Maudsley prescriber's guide, Aug 2026): 231 captioned borderless tables in the book; `find_tables()` flagged 19 pages total, while MinerU found 78 HTML tables in chapter 1 alone vs 2 detectable locally.

When table content matters and the document uses borderless layouts (textbooks, clinical references), find the table pages **by caption, not by ruling**, and route those pages to the mineru skill (cloud VLM):

```python
import re
caption_pages = [i + 1 for i in range(doc.page_count)
                 if re.search(r"Table \d+\.\d+", doc[i].get_text())]
```

Large PDF: physically split out those pages (`pdf_ops.py split doc.pdf --ranges …`) and submit the parts whole — see the mineru skill's Long Documents section for why `--pages` is unreliable.

## Embedded images — extract originals

```python
for img in page.get_images(full=True):
    xref = img[0]
    pix = pymupdf.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3:                     # CMYK -> RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    pix.save(f"img-{xref}.png")
```

- `full=True` includes images referenced but not drawn on the page; filter by `img[7]` (name) or check the `page.get_image_rects(xref)` result if you need on-page positions.
- CLI: `scripts/pymupdf_parse.py file.pdf --images`.

## Render pages/clips to PNG (rasterize — different from extracting embedded images)

```python
# full page at 300 DPI
pix = page.get_pixmap(dpi=300)
pix.save("page.png")

# clip a region (PDF points, origin top-left)
pix = page.get_pixmap(matrix=pymupdf.Matrix(300/72, 300/72),
                      clip=pymupdf.Rect(100, 100, 400, 300))
png_bytes = pix.tobytes("png")     # in-memory
```

- DPI shortcut: `dpi=300` equals `matrix=Matrix(300/72, 300/72)`.
- Landscape/rotated pages are handled automatically by `get_pixmap(clip=...)`.
- Add ~8 px padding around detected bboxes for cleaner crops.
- CLI: `scripts/pdf_ops.py render file.pdf --pages 1-3 --dpi 150`.

## Layout detection — `pymupdf.layout` addon (GNN-based, local)

Needs `pip install pymupdf4llm` (ships the addon).

```python
import pymupdf4llm
import pymupdf.layout as layout_mod
import json

layout_mod.activate()  # MUST call before to_json()

raw = pymupdf4llm.to_json("document.pdf", pages=[0, 1, 2])
result = json.loads(raw)  # returns a JSON string, parse it

for page_data in result["pages"]:
    page_num = page_data["page_number"]  # 1-indexed
    for box in page_data.get("boxes", []):
        print(box["boxclass"], box["x0"], box["y0"], box["x1"], box["y1"])
```

| `boxclass` | Meaning |
|---|---|
| `table` | Detected table region |
| `image` | Embedded image/figure |
| `section-header` | Section or column header |
| `page-header` | Running header/footer |
| `text` | General text block |

### Crop a detected table to PNG

```python
import pymupdf, io
from PIL import Image

doc = pymupdf.open("document.pdf")
page = doc[page_num - 1]  # page_number is 1-indexed
mat = pymupdf.Matrix(300/72, 300/72)
pix = page.get_pixmap(matrix=mat, clip=pymupdf.Rect(x0, y0, x1, y1))
img = Image.open(io.BytesIO(pix.tobytes("png")))
img.save("table.png")
```

## Gotchas

- **Import**: `import pymupdf.layout` (NOT `import pymupdf_layout`).
- `layout_mod.activate()` must run before `pymupdf4llm.to_json()` or `boxes` comes back empty.
- `find_tables()` misses borderless tables by default — `page.find_tables(strategy="text")` exists but is weak in practice; see **Borderless-table blindness** above before trusting a "no tables" result.
- Pixmap `.save()` cannot write CMYK — always convert first (snippet above).
- For VLM-grade layout accuracy with formula recognition, escalate to the mineru skill (cloud).
