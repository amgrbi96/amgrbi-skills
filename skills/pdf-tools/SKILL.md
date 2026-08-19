---
name: pdf-tools
description: 'PDF engineering for generation, modification, form filling, and security. Use when generating PDFs with Puppeteer, modifying/merging/splitting PDFs with pdf-lib, filling PDF forms, implementing PDF security (encrypt/sign/redact), organizing pages (rotate/crop/extract/bookmarks), watermarking or stamping existing PDFs, embedding/extracting images, or compressing PDFs. Use for HTML-to-PDF conversion and document processing pipelines. NOT for content extraction — use the parse-docs skill for that.'
license: MIT
metadata:
  author: oakoss
  version: '1.6'
---

# PDF Tools

Full-lifecycle PDF engineering covering generation, modification, form filling, security, and page organization. Prioritizes JavaScript-first solutions (pdf-lib, unpdf, Puppeteer) with Python/CLI utilities for advanced scenarios.

**When to use**: Generating pixel-perfect PDFs from HTML/React, modifying existing PDFs, filling forms (fillable or non-fillable), securing documents (encrypt/sign/redact), organizing pages (rotate/crop/extract/bookmarks), watermarking or stamping, handling embedded images, or repairing PDFs.

**When NOT to use**:
- **Content extraction** (text, tables, OCR, Markdown) → use the `parse-docs` skill, which routes to `pdf-to-markdown`, `pymupdf-pdf`, `liteparse`, or `mineru`.
- Simple text file processing, image-only manipulation without PDF context, or tasks better handled by a word processor.

## Prerequisites — install check

Each workflow uses a different slice of the toolset. Check what your task needs (see Quick Reference) and install only what's missing — a missing tool is **not** an error unless your workflow reaches for it.

### Check

```bash
# Node.js >= 22 — required by Puppeteer 25.x and unpdf 1.8.x
node --version

# JS packages — run from the project that will use them
for pkg in pdf-lib puppeteer unpdf bullmq @signpdf/signpdf; do
  npm ls --depth=0 "$pkg" >/dev/null 2>&1 && echo "$pkg: ok" || echo "$pkg: MISSING"
done

# Python packages
for mod in pymupdf pdfplumber; do
  python3 -c "import $mod" 2>/dev/null && echo "$mod: ok" || echo "$mod: MISSING"
done

# CLI tools
for cmd in qpdf gs verapdf pdftotext exiftool redis-server; do
  command -v "$cmd" >/dev/null 2>&1 && echo "$cmd: ok" || echo "$cmd: MISSING"
done
```

`redis-server` is only needed for BullMQ batch workflows; `verapdf` only for PDF/A validation.

### Install

```bash
# JS — install into the project you're working in
npm i pdf-lib puppeteer unpdf    # core: modify/merge/split, HTML→PDF, comparison
npm i @cantoo/pdf-lib            # drop-in pdf-lib with encrypted-PDF support
npm i @signpdf/signpdf @signpdf/signer-p12 @signpdf/placeholder-plain \
  @signpdf/utils                 # digital signatures

# Python
pip install pymupdf pdfplumber

# CLI — macOS
brew install qpdf ghostscript verapdf poppler exiftool redis

# CLI — Debian/Ubuntu (verapdf is not packaged; download from docs.verapdf.org)
sudo apt install qpdf ghostscript poppler-utils libimage-exiftool-perl redis-server
```

Puppeteer downloads its own Chromium at install — no separate Chrome needed. If the browser is missing (e.g. `PUPPETEER_SKIP_DOWNLOAD` was set), run `npx puppeteer browsers install chrome`.

## Quick Reference

| Task                       | Tool                          | Key Point                                                                  |
| -------------------------- | ----------------------------- | -------------------------------------------------------------------------- |
| Generate PDF from HTML     | Puppeteer / Playwright        | `page.pdf()`; settle fonts via `waitForNetworkIdle()` (Puppeteer) or `networkidle` (Playwright) |
| Modify, merge, split       | pdf-lib (or `@pdfme/pdf-lib`) | Byte-level PDF manipulation in JS                                          |
| Fill fillable forms        | pdf-lib (or `@pdfme/pdf-lib`) | Inspect AcroForm fields before writing                                     |
| Fill non-fillable forms    | Python annotation scripts     | Visual analysis + bounding box annotations                                 |
| Encrypt PDF                | qpdf                          | AES-256: `qpdf --encrypt user owner 256 --`                                |
| Repair corrupted PDF       | qpdf                          | `qpdf input.pdf --replace-input`                                           |
| Merge thousands of files   | pymupdf                       | `insert_pdf` into one doc; lighter than a headless browser                 |
| Rotate, delete, crop pages | pdf-lib                       | `setRotation(degrees(90))`, `removePage`, `setCropBox`                     |
| Extract page subset        | pdf-lib                       | `copyPages(src, indices)` into a new document                              |
| Bookmarks / outlines       | pymupdf                       | `set_toc([[level, title, page]])` — 1-based pages                          |
| Watermark / page numbers   | pdf-lib                       | `drawText` with `opacity` looped over pages                                |
| Stamp from another PDF     | pymupdf                       | `show_pdf_page` places a stamp/seal page                                   |
| Embed / extract images     | pdf-lib / pymupdf             | `embedPng`; `get_images` + `Pixmap`                                        |
| Compress PDF               | ghostscript                   | `-dPDFSETTINGS=/ebook` downsamples to 150 dpi                              |
| Batch queue processing     | BullMQ + unpdf                | Redis-backed with retry, concurrency, progress tracking                    |
| PDF/A archival compliance  | ghostscript + verapdf         | `gs -dPDFA=2` for conversion; verapdf for validation                       |
| Tagged PDF (accessibility) | Puppeteer                     | `tagged: true` maps HTML semantics to PDF structure tags                   |
| Digital signatures         | @signpdf/\*                   | PKCS#7 signing with P12 certificates                                       |
| PDF comparison             | unpdf + diff / pixelmatch     | Text diff or pixel-level visual diff between versions                      |
| Secure redaction           | pymupdf                       | `apply_redactions()` removes content bytes, not just visual overlay        |

> **Content extraction** (text, tables, OCR, Markdown) is handled by the `parse-docs` skill — don't use the tools below for that.

## Common Mistakes

| Mistake                                                | Correct Pattern                                                   |
| ------------------------------------------------------ | ----------------------------------------------------------------- |
| Using canvas drawing commands for PDF generation       | Use Puppeteer/Playwright with HTML/CSS templates                  |
| Running Puppeteer in edge/serverless environments      | Use unpdf for edge; Puppeteer requires full Node.js               |
| Extracting complex layouts with basic text parsers     | Use AI-assisted OCR or pdfplumber for multi-column text           |
| Storing unencrypted PDFs with PII in public storage    | Apply AES-256 encryption via qpdf before storage                  |
| Relying on `window.print()` for server-side generation | Use headless browser APIs (`page.pdf()`) for deterministic output |
| Complex layouts parsed with basic tools               | Route to the parse-docs skill (liteparse/mineru)                  |
| Skipping font embedding in containerized environments  | Embed Google Fonts or WOFF2 files with Puppeteer                  |
| Writing to flattened PDF form fields                   | Inspect AcroForm fields with pdf-lib before writing               |
| Using unmaintained `pdf-lib` for encrypted PDFs        | Use `@cantoo/pdf-lib` fork which adds encrypted PDF support       |

## Delegation

- **Inspect PDF structure and diagnose extraction issues**: Use `Explore` agent to examine AcroForm fields, encoding, and metadata
- **Build end-to-end document processing pipelines**: Use `Task` agent to implement extraction, transformation, and generation workflows
- **Design PDF architecture for a new system**: Use `Plan` agent to select tools and plan extraction, generation, or modification strategies

## References

- [High-Fidelity Generation](references/high-fidelity-generation.md) -- Puppeteer HTML-to-PDF, CSS print tips, React templates, browser pooling
- [Legacy Utilities](references/legacy-utilities.md) -- pdfplumber, pymupdf, qpdf, poppler-utils for batch and forensic tasks
- [Page Operations](references/page-operations.md) -- Rotate/delete/crop/extract pages, bookmarks, links, attachments, linearize, decrypt
- [Watermarking and Overlays](references/watermarking-and-overlays.md) -- Watermarks, page numbers on existing PDFs, stamping pages from other documents
- [Images and Optimization](references/images-and-optimization.md) -- Embed/extract images, render pages, thumbnails, compression
- [Form Filling](references/form-filling.md) -- Fillable field extraction, non-fillable annotation workflow, validation scripts
- [Batch Processing and Accessibility](references/batch-and-accessibility.md) -- Queue-based batch processing, PDF/A compliance, tagged PDFs, digital signatures, comparison, redaction

## Self-Test

After changing SKILL.md or any reference, run the offline self-test. It checks structure (dead links, orphan files), doc drift (deprecated API patterns, parse-docs routing consistency, the prerequisites Check block), and live-executes the documented example scripts against fixtures. Missing deps SKIP with an install hint — they never fail:

```bash
python3 evals/selftest.py
```
