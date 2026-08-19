# Security, Metadata, TOC, Embedded Files

Load when: encrypting/decrypting, reading or writing metadata/TOC/bookmarks, or attaching files to a PDF.

One-shot versions are in the CLI:

```bash
scripts/pdf_ops.py info    doc.pdf                     # pages/metadata/TOC/encryption
scripts/pdf_ops.py meta    doc.pdf --set title=X -o o.pdf
scripts/pdf_ops.py toc     doc.pdf --json toc.json -o o.pdf
scripts/pdf_ops.py toc     doc.pdf                    # read TOC as JSON
scripts/pdf_ops.py encrypt doc.pdf --user-pw secret -o enc.pdf
scripts/pdf_ops.py decrypt enc.pdf --password secret -o dec.pdf
```

Assumes `import pymupdf`.

## Encryption

```python
doc.save("enc.pdf",
         encryption=pymupdf.PDF_ENCRYPT_AES_256,   # or AES_128, RC4 variants
         owner_pw="owner",                          # full-permission password
         user_pw="reader")                          # open password
```

- `PDF_ENCRYPT_AES_256` is the modern default choice.
- Permission flags (`pymupdf.PDF_PERM_ACCESSIBLE`, `PDF_PERM_PRINT`, …) can be OR-ed via `permissions=` on the owner password; by default the user of `user_pw` gets no extra permissions.
- The CLI's `encrypt` uses AES-256 with `owner_pw` defaulting to `user_pw`.

## Decryption / opening encrypted PDFs

```python
doc = pymupdf.open("enc.pdf")
if doc.needs_pass:
    ok = doc.authenticate("reader")    # returns int > 0 on success, 0 on failure
    if not ok:
        raise SystemExit("wrong password")

doc.save("dec.pdf", encryption=pymupdf.PDF_ENCRYPT_NONE)  # strip encryption
```

- There is no `open(path, password=...)` — always open, check `needs_pass`, then `authenticate()`.

## Metadata

```python
print(doc.metadata)   # dict: title, author, subject, keywords, creator,
                      # producer, creationDate, modDate, format, version...

doc.set_metadata({"title": "New title", "author": "Ahmad"})
doc.save("out.pdf")
```

- Dates use `D:YYYYMMDDHHmmSS` PDF strings; garbage=3 on save removes old XMP traces.

## TOC / bookmarks

```python
toc = doc.get_toc()            # [[level, title, page_1indexed], ...]
doc.set_toc([[1, "Intro", 1],
             [2, "Details", 2],
             [1, "End", 3]])
doc.save("out.pdf")
```

- Levels 1–6; out-of-range pages raise.
- `doc.set_toc([])` removes the whole outline.
- Generate from headings: scan spans (see `extract.md`) and build `[lvl, text, page]` rows.

## Embedded files (attachments)

```python
# attach
doc.embfile_add("data.csv", open("data.csv", "rb").read(), filename="data.csv")

# list & extract
for item in doc.embfile_names():
    print(item, doc.embfile_info(item)["size"])
    open(f"extracted-{item}", "wb").write(doc.embfile_get(item))
```

## Links

```python
for link in doc[0].get_links():     # dicts: kind, from (rect), uri/page
    print(link)
doc[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 72, 200, 90),
                     "uri": "https://example.com"})
```

## Gotchas

- `save()` with encryption requires saving to a **new** path while the original is open.
- `authenticate()` must be called before any page access on an encrypted file.
- `set_metadata` only accepts the documented keys — unknown keys are ignored silently.
- PDF permissions are advisory for some viewers; AES + passwords is the real control.
