# Creating PDFs

Load when: generating PDFs from scratch — text, fonts, images, vector drawing, or HTML content.

Assumes `import pymupdf`. For pixel-perfect HTML→PDF at scale, prefer the pdf-tools skill (Puppeteer); this file is the pure-Python path.

## New document, standard page sizes

```python
doc = pymupdf.open()
page = doc.new_page()                          # A4 portrait, 595 x 842 pt
page = doc.new_page(width=612, height=792)     # US Letter explicit
page = doc.new_page(width=pymupdf.paper_rect("a3").width,
                    height=pymupdf.paper_rect("a3").height)
```

## Text

```python
# single line at a point
page.insert_text((72, 96), "Title", fontsize=20, fontname="hebo")

# wrapped inside a box; returns unused height (negative = overflow)
left = page.insert_textbox(pymupdf.Rect(72, 120, 523, 400),
                           "Long paragraph text...", fontsize=11,
                           align=pymupdf.TEXT_ALIGN_LEFT)
if left < 0:
    print("text did not fit")
```

- Built-in fonts: `helv`, `hebo` (bold), `heit` (italic), `tiro` (serif), plus CJK `china-s`, `china-ss`.
- Base-14 font aliases map to standard PDF fonts — no embedding needed.

## Fonts & TextWriter (precise placement, reuse across pages)

```python
tw = pymupdf.TextWriter(page.rect, color=(0.1, 0.1, 0.1))
font = pymupdf.Font("helv")
tw.append((72, 96), "Precise text", font=font, fontsize=12)
tw.write_text(page)
```

## Images

```python
page.insert_image(pymupdf.Rect(72, 120, 272, 220), filename="pic.png")
# or in-memory: page.insert_image(rect, stream=png_bytes)
# keep aspect: compute the rect from pix.width/pix.height
```

## Vector drawing

```python
shape = page.new_shape()
shape.draw_rect(pymupdf.Rect(72, 400, 200, 450))
shape.draw_line((72, 500), (300, 500))
shape.draw_circle((150, 600), 40)
shape.finish(color=(0, 0, 0.8), fill=(0.9, 0.9, 1), width=1.5)  # stroke+fill params
shape.commit()   # REQUIRED — nothing renders without it
```

Convenience shortcuts (auto-commit): `page.draw_rect(rect)`, `page.draw_line(p1, p2)`, `page.draw_circle(center, radius)`.

## HTML → PDF (Story API)

```python
HTML = """
<h2>Report</h2>
<p>Simple <b>styled</b> paragraph.</p>
<table><tr><td>cell</td><td>2</td></tr></table>
"""
story = pymupdf.Story(html=HTML)
writer = pymupdf.DocumentWriter("out.pdf")
mediabox = pymupdf.paper_rect("a4")
where = mediabox + (36, 36, -36, -36)              # 36 pt margins
more = 1
while more:
    device = writer.begin_page(mediabox)
    more, _ = story.place(where)
    story.draw(device)
    writer.end_page()
writer.close()
```

- Story handles pagination, basic CSS, tables, and images referenced by path.
- Limited CSS subset — complex layouts belong to Puppeteer (pdf-tools skill).

## Images → PDF

```python
img = pymupdf.open("pic.png")       # PyMuPDF opens images as 1-page docs
pdf_bytes = img.convert_to_pdf()    # then insert into a page if needed
```

## Gotchas

- `shape.commit()` (or the `page.draw_*` shortcuts) — forgetting it silently renders nothing.
- `insert_text` y-coordinate is the **baseline**, not the top of the text.
- `insert_textbox` returns leftover height; negative means overflow (text is truncated).
- Story + DocumentWriter requires the begin/end_page loop even for single-page output.
