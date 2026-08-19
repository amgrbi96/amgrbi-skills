# Page & Document Manipulation

Load when: merging, splitting, reordering, rotating, cropping, or deleting pages.

Most one-shot operations are already in the CLI:

```bash
scripts/pdf_ops.py merge  --inputs a.pdf b.pdf -o merged.pdf
scripts/pdf_ops.py split  big.pdf --outroot out/ --ranges 1-10,11-20
scripts/pdf_ops.py rotate in.pdf --pages 1-3 --deg 90 -o out.pdf
scripts/pdf_ops.py delete in.pdf --pages 2,5-7 -o out.pdf
```

All examples assume `import pymupdf`.

## Merge / append documents

```python
out = pymupdf.open()
for path in ["a.pdf", "b.pdf"]:
    src = pymupdf.open(path)
    out.insert_pdf(src)           # full document
    src.close()
out.save("merged.pdf", garbage=3, deflate=True)
```

- Partial insert: `out.insert_pdf(src, from_page=0, to_page=4)` (0-indexed, inclusive).
- Insert at a position: `out.insert_pdf(src, start_at=2)`.

## Split / extract page subsets

```python
src = pymupdf.open("big.pdf")

# pages 1-10 (0-indexed slice) to a new file
part = pymupdf.open()
part.insert_pdf(src, from_page=0, to_page=9)
part.save("part1.pdf")

# in-place selection (keeps pages, drops the rest)
src.select([0, 1, 2, 5])          # 0-indexed, any order — also reorders
src.save("subset.pdf")
```

## Reorder pages

```python
doc.select([2, 0, 1])  # new order: old page 3, then 1, then 2
doc.save("reordered.pdf")
```

## Rotate

```python
doc[0].set_rotation(90)   # 0, 90, 180, 270 only
doc.save("rot.pdf")
```

## Crop (change the visible page area)

```python
page = doc[0]
page.set_cropbox(pymupdf.Rect(50, 50, 500, 700))  # PDF points
doc.save("cropped.pdf")
```

- CropBox persists to all viewers; `set_mediabox()` changes the physical page instead.

## Copy a single page between docs

```python
src = pymupdf.open("a.pdf"); dst = pymupdf.open("b.pdf")
dst.insert_pdf(src, from_page=2, to_page=2)
```

## Gotchas

- `doc.save()` refuses to overwrite an existing file — delete it first or save to a new path (the CLI does this for you).
- `select()` / `delete_page()` mutate the open document; keep page indices straight by computing them before mutating.
- Repeatedly saving with `garbage=3` keeps file sizes down after deletions.
- In-place edits (same input and output path) are not supported while the doc is open — write to a temp name and rename.
