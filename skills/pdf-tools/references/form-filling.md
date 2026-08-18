---
title: Form Filling
description: Fillable PDF form field extraction and filling with pdf-lib, non-fillable form annotation workflow with visual analysis and bounding box validation
tags:
  [forms, fillable, annotations, AcroForm, bounding-box, pdf-lib, validation]
---

## Determining Form Type

First check whether the PDF has fillable AcroForm fields with pdf-lib:

```js
// inspect-form.js — node inspect-form.js input.pdf
import { PDFDocument } from 'pdf-lib';
import * as fs from 'node:fs/promises';

const pdf = await PDFDocument.load(await fs.readFile(process.argv[2]));
const fields = pdf.getForm().getFields();

console.log(fields.length === 0 ? 'NON-FILLABLE' : 'FILLABLE');
for (const field of fields) {
  console.log(JSON.stringify({ name: field.getName(), type: field.constructor.name }));
}
```

Encrypted PDFs throw on load with original pdf-lib — use the `@cantoo/pdf-lib` fork with `PDFDocument.load(bytes, { password })`. Based on the result, follow the fillable or non-fillable workflow below.

## Fillable Forms Workflow

### Step 1: Extract Field Information

Extend the inspection script to dump radio/checkbox options too:

```js
import { PDFRadioGroup, PDFDropdown } from 'pdf-lib';

for (const field of fields) {
  const entry = { field_id: field.getName(), type: field.constructor.name };
  if (field instanceof PDFRadioGroup || field instanceof PDFDropdown) {
    entry.options = field.getOptions();
  }
  console.log(JSON.stringify(entry));
}
```

### Step 2: Visual Analysis

Render pages as images and match field names to their visual purpose:

```python
# render_pages.py — python render_pages.py input.pdf outdir/
import pymupdf, os, sys

doc = pymupdf.open(sys.argv[1])
os.makedirs(sys.argv[2], exist_ok=True)
for i, page in enumerate(doc, start=1):
    page.get_pixmap(dpi=150).save(f"{sys.argv[2]}/page-{i}.png")
```

Analyze the images to determine what each field represents.

### Step 3: Create Field Values

Create a `field_values.json` mapping each field to its intended value:

```json
[
  { "field_id": "last_name", "value": "Simpson" },
  { "field_id": "Checkbox12", "value": true },
  { "field_id": "gender_group", "value": "Male" }
]
```

For radio groups and dropdowns, use one of the exact values from `getOptions()`.

### Step 4: Fill the Form

```js
// fill-form.js — node fill-form.js input.pdf field_values.json output.pdf
import {
  PDFDocument,
  PDFTextField,
  PDFCheckBox,
  PDFRadioGroup,
  PDFDropdown,
} from 'pdf-lib';
import * as fs from 'node:fs/promises';

const pdf = await PDFDocument.load(await fs.readFile(process.argv[2]));
const form = pdf.getForm();
const values = JSON.parse(await fs.readFile(process.argv[3], 'utf8'));

for (const { field_id, value } of values) {
  const field = form.getField(field_id); // throws on unknown id — fix and retry
  if (field instanceof PDFTextField) field.setText(String(value));
  else if (field instanceof PDFCheckBox) value ? field.check() : field.uncheck();
  else if (field instanceof PDFRadioGroup) field.select(String(value));
  else if (field instanceof PDFDropdown) field.select(String(value));
}

// form.flatten(); // uncomment to make values permanent and non-editable

await fs.writeFile(process.argv[4], await pdf.save());
```

## Non-Fillable Forms Workflow

For PDFs without form fields, place text at visual positions with PyMuPDF.

### Step 1: Visual Analysis

Render pages with the `render_pages.py` script above, then determine a bounding box for each entry area. When reading pixel coordinates off a rendered image, convert to PDF points: `pt = px * 72 / dpi` (e.g. divide by `150 / 72` at 150 dpi).

Label and entry bounding boxes must not intersect. Common form layouts:

| Layout                              | Entry Area Location             |
| ----------------------------------- | ------------------------------- |
| Label inside box (`Name: ____`)     | Right of label, to edge of box  |
| Label before line (`Email: ___`)    | Above the line, full width      |
| Label under line (line then `Name`) | Above the line, full width      |
| Checkboxes (`Yes [] No []`)         | Small square only, not the text |

### Step 2: Create fields.json

Boxes are `[x0, y0, x1, y1]` in PDF points, origin bottom-left:

```json
{
  "form_fields": [
    {
      "page_number": 1,
      "description": "Last name entry",
      "entry_bounding_box": [100, 125, 280, 142],
      "entry_text": { "text": "Johnson", "font_size": 14 }
    },
    {
      "page_number": 1,
      "description": "Age verification checkbox",
      "entry_bounding_box": [140, 525, 155, 540],
      "entry_text": { "text": "X" }
    }
  ]
}
```

### Step 3: Validate Boxes

Draw the entry boxes onto the PDF and render for visual review:

```python
# validate_boxes.py — python validate_boxes.py input.pdf fields.json review.pdf
import pymupdf, json, sys

doc = pymupdf.open(sys.argv[1])
fields = json.load(open(sys.argv[2]))["form_fields"]

for f in fields:
    page = doc[f["page_number"] - 1]
    page.draw_rect(pymupdf.Rect(*f["entry_bounding_box"]), color=(1, 0, 0), width=1)

doc.save(sys.argv[3])
```

Render `review.pdf` with `render_pages.py` and check that red rectangles cover only input areas — no label text. Iterate `fields.json` until correct.

### Step 4: Fill the Form

```python
# fill_annotations.py — python fill_annotations.py input.pdf fields.json output.pdf
import pymupdf, json, sys

doc = pymupdf.open(sys.argv[1])
fields = json.load(open(sys.argv[2]))["form_fields"]

for f in fields:
    page = doc[f["page_number"] - 1]
    t = f["entry_text"]
    page.insert_textbox(
        pymupdf.Rect(*f["entry_bounding_box"]),
        t["text"],
        fontsize=t.get("font_size", 12),
        color=(0, 0, 0),
    )

doc.save(sys.argv[3])
```

## Common Issues

| Issue                         | Fix                                                              |
| ----------------------------- | ---------------------------------------------------------------- |
| Field IDs not matching        | Re-run the inspection script; use exact `field_id` values        |
| Flattened form fields         | Fields cannot be filled; use annotation workflow instead         |
| Overlapping bounding boxes    | Re-analyze images; ensure label and entry boxes do not intersect |
| Text too large for entry area | Reduce `font_size`, or switch to `insert_textbox` with a taller box |
| Checkbox not rendering        | For fillable forms call `check()`; for print-style boxes write "X" |
