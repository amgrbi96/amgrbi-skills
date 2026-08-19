---
title: Watermarking and Overlays
description: Text and image watermarks, page numbers on existing PDFs, and stamping pages from other documents with pdf-lib and pymupdf
tags: [watermark, stamp, overlay, page-numbers, bates, headers]
---

These workflows apply to **existing** PDFs. For headers/footers at generation time, use Puppeteer's `displayHeaderFooter` instead (see [High-Fidelity Generation](high-fidelity-generation.md)).

## Text Watermark on Every Page

```js
// watermark.js — node watermark.js input.pdf output.pdf
import { PDFDocument, StandardFonts, rgb, degrees } from 'pdf-lib';
import * as fs from 'node:fs/promises';

const pdf = await PDFDocument.load(await fs.readFile(process.argv[2]));
const font = await pdf.embedFont(StandardFonts.HelveticaBold);

for (const page of pdf.getPages()) {
  const { width, height } = page.getSize();
  page.drawText('CONFIDENTIAL', {
    x: width / 2 - 120,
    y: height / 2,
    size: 48,
    font,
    color: rgb(0.8, 0.2, 0.2),
    opacity: 0.3,
    rotate: degrees(45),
  });
}

await fs.writeFile(process.argv[3], await pdf.save());
```

Drawn text lands **on top of** existing content — keep `opacity` at 0.2–0.4 so body text stays readable.

## Page Numbers on an Existing PDF

```js
import { StandardFonts, rgb } from 'pdf-lib';

const font = await pdf.embedFont(StandardFonts.Helvetica);
pdf.getPages().forEach((page, i) => {
  const { width } = page.getSize();
  page.drawText(`${i + 1} / ${pdf.getPageCount()}`, {
    x: width / 2 - 20,
    y: 24,
    size: 10,
    font,
    color: rgb(0.3, 0.3, 0.3),
  });
});
```

For Bates-style numbering (unique ID per page), derive the label from the index: `String(i + 1).padStart(6, '0')`.

## Stamp a Page from Another PDF

Place a prepared stamp/seal/signature page onto every page with pymupdf:

```python
# stamp.py — python stamp.py input.pdf stamp.pdf output.pdf
import pymupdf

doc = pymupdf.open("input.pdf")
stamp = pymupdf.open("stamp.pdf")  # e.g. an "APPROVED" seal

for page in doc:
    page.show_pdf_page(pymupdf.Rect(400, 700, 550, 780), stamp, 0)

doc.save("output.pdf")
```

pdf-lib equivalent — embed the page, then draw it:

```js
const embedded = await pdf.embedPage(stampDoc.getPage(0));
page.drawPage(embedded, { x: 300, y: 600 });
```

## Image Stamps

Logos, seals, and QR codes: embed the image with pdf-lib's `embedPng`/`embedJpg` and `drawImage` per page — see [Images and Optimization](images-and-optimization.md).

## Tool Selection

| Task                      | Tool         | Notes                                  |
| ------------------------- | ------------ | -------------------------------------- |
| Text watermark            | pdf-lib      | `drawText` with `opacity` + `rotate`   |
| Page numbers / Bates      | pdf-lib      | Loop pages, `drawText` per index       |
| Stamp from another PDF    | pymupdf      | `show_pdf_page` places a whole page    |
| Image stamp (logo/QR)     | pdf-lib      | `drawImage(embedPng(...))`             |

## Troubleshooting

| Issue                     | Fix                                                        |
| ------------------------- | ---------------------------------------------------------- |
| Watermark obscures text   | Lower `opacity` (0.2–0.4); pdf-lib draws on top            |
| Stamp stretched           | Match the `Rect`/`drawPage` aspect ratio to the stamp page |
| Rotated pages stamp wrong | Watermark coordinates ignore `setRotation`; test per page  |
