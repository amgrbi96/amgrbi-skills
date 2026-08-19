---
title: Page Operations
description: Rotate, delete, reorder, extract and crop pages; bookmarks and outlines with pypdf; links and attachments with pymupdf; linearization and decryption with qpdf
tags: [pages, rotate, crop, extract, outline, bookmarks, links, attachments, linearize, decrypt]
---

## Page-Level Operations

Rotate, delete, and crop with pdf-lib:

```js
// pages.js — node pages.js input.pdf output.pdf
import { PDFDocument, degrees } from 'pdf-lib';
import * as fs from 'node:fs/promises';

const pdf = await PDFDocument.load(await fs.readFile(process.argv[2]));

pdf.removePage(1); // delete page 2 (0-based index)

const page = pdf.getPage(0);
page.setRotation(degrees(90)); // must be a multiple of 90
page.setCropBox(0, 0, 595.28, 841.89); // A4 in points, origin bottom-left

await fs.writeFile(process.argv[3], await pdf.save());
```

`setCropBox` sets the visible area (most common); `setMediaBox` sets the underlying canvas.

Extract a subset of pages to a new file:

```js
const src = await PDFDocument.load(await fs.readFile('input.pdf'));
const out = await PDFDocument.create();
const pages = await out.copyPages(src, [0, 2, 3]); // keep pages 1, 3, 4
pages.forEach((p) => out.addPage(p));
await fs.writeFile('extracted.pdf', await out.save());
```

Bulk page reordering across thousands of files is lighter with pypdf (see [Legacy Utilities](legacy-utilities.md)).

## Bookmarks and Outlines

Add a navigation outline with pypdf:

```python
# outline.py — python outline.py input.pdf output.pdf
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()
writer.append(reader)  # copies all pages

writer.add_outline_item("Cover", 0)
ch1 = writer.add_outline_item("Chapter 1", 1)
writer.add_outline_item("Section 1.1", 2, parent=ch1)

with open("output.pdf", "wb") as f:
    writer.write(f)
```

Page numbers are 0-based. For generated documents, prefer setting bookmarks from a known heading map rather than guessing page positions.

## Links

Add hyperlinks and internal jumps with pymupdf:

```python
import pymupdf

doc = pymupdf.open("input.pdf")
page = doc[0]

page.insert_link({
    "kind": pymupdf.LINK_URI,   # external URL
    "from": pymupdf.Rect(100, 700, 300, 720),
    "uri": "https://example.com",
})
page.insert_link({
    "kind": pymupdf.LINK_GOTO,  # internal jump
    "from": pymupdf.Rect(100, 650, 300, 670),
    "page": 2,                  # 0-based target page
})

doc.save("linked.pdf")
```

The `from` rectangle is the clickable area, not a visual element — the link text must already exist in the page content.

## Attachments

Embed files into a PDF and read them back with pymupdf:

```python
import pymupdf

doc = pymupdf.open("input.pdf")
with open("receipt.csv", "rb") as f:
    doc.embfile_add("receipt.csv", f.read(), filename="receipt.csv")

print(doc.embfile_names())          # ['receipt.csv']
data = doc.embfile_get("receipt.csv")  # bytes back out

doc.save("with-attachment.pdf")
```

For PDF/A-3 e-invoicing (ZUGFeRD/Factur-X), attachments must ride on a PDF/A-3 document — see the PDF/A section of [Batch Processing and Accessibility](batch-and-accessibility.md).

## Linearization and Decryption

```bash
# Fast web view — browsers stream page-by-page before the full download
qpdf --linearize input.pdf linearized.pdf

# Remove password protection (requires the current password)
qpdf --password=SECRET --decrypt input.pdf decrypted.pdf
```

To modify an encrypted PDF in JS instead, load it with `@cantoo/pdf-lib` and `{ password }` — see the maintenance note in [Legacy Utilities](legacy-utilities.md).

## Tool Selection

| Task                    | Tool         | Notes                                   |
| ----------------------- | ------------ | --------------------------------------- |
| Rotate/delete/crop page | pdf-lib      | `setRotation(degrees(n))`, `setCropBox` |
| Extract page subset     | pdf-lib      | `copyPages(src, indices)`               |
| Bookmarks/outline       | pypdf        | `add_outline_item(title, page, parent)` |
| Links                   | pymupdf      | `insert_link` with `LINK_URI`/`LINK_GOTO` |
| Attachments             | pymupdf      | `embfile_add`/`embfile_get`             |
| Linearize/decrypt       | qpdf         | `--linearize`, `--password=... --decrypt` |

## Troubleshooting

| Issue                       | Fix                                                     |
| --------------------------- | ------------------------------------------------------- |
| Rotation must be 0/90/180/270 | `degrees()` values outside multiples of 90 are invalid |
| Link area not clickable     | `from` rect must overlap existing text and page bounds  |
| Outline points to wrong page | Page numbers are 0-based; verify before writing        |
