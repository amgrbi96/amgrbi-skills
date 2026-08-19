# Annotations, Forms, Redaction

Load when: adding highlights/notes/comments, filling or inspecting form fields, or irreversibly removing content.

All examples assume `import pymupdf` and `doc = pymupdf.open("file.pdf")` opened on a **writable copy** (never the original).

## Annotations

```python
page = doc[0]

# highlight every hit of a phrase (search returns rects)
for rect in page.search_for("sensitive term"):
    page.add_highlight_annot(rect)

# other types
page.add_underline_annot(rect)
page.add_strikeout_annot(rect)
page.add_squiggly_annot(rect)
page.add_text_annot((72, 100), "Review note", icon="Comment")  # sticky note
page.add_free_text_annot(rect, "margin text", fontsize=10)

doc.save("out.pdf")
```

- Each `add_*_annot` returns the annot — chain `.set_colors()`, `.set_opacity(0.5)`, `.update()` to style it.
- Search hits spanning lines return quads; `add_highlight_annot` accepts both `Rect` and `Quad`.

### List / modify / delete

```python
for annot in page.annots():           # or doc.annots(pages=[0]) across pages
    print(annot.type, annot.rect, annot.info["content"])
    if annot.type[0] == 8:            # 8 = Highlight
        page.delete_annot(annot)
```

Type numbers: 8=Highlight, 9=Underline, 10=Strikeout, 11=Squiggly, 3=FreeText, 1=Text(note).

## Forms (AcroForm widgets)

```python
print(doc.is_form_pdf)                # True if it has form fields

for page in doc:
    for widget in page.widgets():
        print(widget.field_name, widget.field_type_string, widget.field_value)
        if widget.field_type_string == "Text":
            widget.field_value = "Ahmad"
            widget.update()           # REQUIRED to persist the value
doc.save("filled.pdf")
```

- Field types: `Text`, `CheckBox`, `ComboBox`, `ListBox`, `RadioButton`, `Signature`.
- Checkboxes: set `widget.field_value = True` (or the export value), then `widget.update()`.
- Signature fields cannot be signed with PyMuPDF — use pdf-tools (`@signpdf/signpdf`).

### Create a form field

```python
widget = pymupdf.Widget()
widget.field_name = "email"
widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
widget.rect = pymupdf.Rect(100, 100, 400, 125)
page.add_widget(widget)
doc.save("with-form.pdf")
```

## Redaction (irreversible removal)

```python
page = doc[0]
for rect in page.search_for("secret"):
    page.add_redact_annot(rect)       # mark regions
page.apply_redactions()               # ACTUALLY REMOVES content — irreversible
doc.save("redacted.pdf")
```

- `apply_redactions(images=2)` (default) also redacts image pixels inside the marked regions; `images=0` leaves images untouched.
- Text inside the rect is excised from the content stream — copy/paste won't recover it.
- Always verify: re-open the output and `search_for()` the removed term; expect zero hits.
- Visual black boxes drawn over text are NOT redaction — content remains extractable.

## Gotchas

- `widget.update()` / `annot.update()` are required — mutating attributes alone writes nothing.
- `page.annots()` excludes widgets; iterate `page.widgets()` for form fields.
- Incremental saves (`doc.save(..., incremental=True)`) preserve digital signatures but require saving to the same file path.
- For certified/signature workflows, escalate to the pdf-tools skill.
