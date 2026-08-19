---
title: Images and Optimization
description: Embed images into PDFs with pdf-lib, render and extract images with pymupdf and poppler, and compress PDFs with ghostscript
tags: [images, embed, extract, rasterize, thumbnails, compression, ghostscript]
---

## Embed an Image

```js
// add-image.js — node add-image.js input.pdf logo.png output.pdf
import { PDFDocument } from 'pdf-lib';
import * as fs from 'node:fs/promises';

const pdf = await PDFDocument.load(await fs.readFile(process.argv[2]));
const png = await pdf.embedPng(await fs.readFile(process.argv[3]));

const page = pdf.getPage(0);
page.drawImage(png, { x: 40, y: 760, width: 120, height: 60 });

await fs.writeFile(process.argv[4], await pdf.save());
```

pdf-lib embeds PNG and JPEG only (`embedPng`/`embedJpg`) — convert WebP/GIF/TIFF first. Match `width`/`height` to the image's aspect ratio to avoid stretching.

## Render Pages to Images

pymupdf (also used by the form-filling visual analysis workflow):

```python
import pymupdf

doc = pymupdf.open("input.pdf")
for i, page in enumerate(doc, start=1):
    page.get_pixmap(dpi=150).save(f"page-{i}.png")
```

poppler, when you want PNGs from the shell:

```bash
pdftoppm -png -r 150 input.pdf page   # page-1.png, page-2.png, ...
```

For thumbnails, drop the DPI (`get_pixmap(dpi=36)`, `pdftoppm -r 36`).

## Extract Embedded Images

```python
import pymupdf

doc = pymupdf.open("input.pdf")
seen = set()
for image in doc[0].get_images(full=True):
    xref = image[0]
    if xref in seen:  # same xref may appear multiple times per page
        continue
    seen.add(xref)
    pymupdf.Pixmap(doc, xref).save(f"img-{xref}.png")
```

If output colors look inverted or washed out, the image is CMYK or has an alpha mask — convert to RGB first:

```python
pix = pymupdf.Pixmap(doc, xref)
if pix.colorspace and pix.colorspace.n > 3:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
```

## Compression

Downsample images to shrink image-heavy files:

```bash
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.7 -dPDFSETTINGS=/ebook \
  -dNOPAUSE -dQUIET -dBATCH -sOutputFile=compressed.pdf input.pdf
```

| `-dPDFSETTINGS` | Target | Use for                    |
| --------------- | ------ | -------------------------- |
| `/screen`       | 72 dpi | Screen-only reading        |
| `/ebook`        | 150 dpi | General purpose (default pick) |
| `/printer`      | 300 dpi | Office printing            |
| `/prepress`     | 300 dpi | Print, preserves color     |

Structural compression without touching images — regroup objects into object streams:

```bash
qpdf --object-streams=generate --compress-streams=y input.pdf compressed.pdf
```

Compression trades quality for size — keep the original and verify the output visually before replacing anything.

## Tool Selection

| Task                  | Tool             | Notes                                    |
| --------------------- | ---------------- | ---------------------------------------- |
| Embed PNG/JPEG        | pdf-lib          | `embedPng`/`embedJpg` + `drawImage`      |
| Render page → image   | pymupdf / poppler | `get_pixmap(dpi=...)` / `pdftoppm -r`   |
| Extract embedded image | pymupdf         | `get_images` + `Pixmap(doc, xref)`       |
| Compress image-heavy  | ghostscript      | `-dPDFSETTINGS=/ebook`                   |
| Compress structure    | qpdf             | `--object-streams=generate`              |

## Troubleshooting

| Issue                    | Fix                                              |
| ------------------------ | ------------------------------------------------ |
| Extracted PNG discolored | CMYK colorspace — wrap in `Pixmap(csRGB, pix)`   |
| Embedded image stretched | Set `width`/`height` to the source aspect ratio  |
| Small PDF grew after gs  | `/ebook` targets image-heavy docs; skip text PDFs |
| WebP/GIF rejected        | pdf-lib is PNG/JPEG only — convert first         |
