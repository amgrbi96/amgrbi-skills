---
name: pdf-tools
description: 'PDF output-side engineering for what pymupdf cannot do: HTML-to-PDF generation with Puppeteer (print CSS, web fonts, React templates), PDF/A archival compliance via ghostscript and verapdf, PKCS#7 digital signing with @signpdf, and qpdf encryption/repair/linearization. NOT for content extraction — use the parse-docs skill. Routine page edits (merge, split, rotate, crop, watermark, forms, redaction) need no skill — use pymupdf directly.'
license: MIT
metadata:
  author: oakoss
  version: '2.0'
---

# PDF Tools

The thin slice of PDF engineering that needs a real browser, an archival converter, a signer, or qpdf. Everything else — merging, page edits, watermarks, form filling, redaction, stamping — is one or two pymupdf calls; no skill required.

**When to use**: Generating pixel-perfect PDFs from HTML/React, converting or validating PDF/A, tagging PDFs for accessibility, digitally signing documents, or repairing/encrypting/linearizing PDFs with qpdf.

**When NOT to use**:
- **Content extraction** (text, tables, OCR, Markdown) → use the `parse-docs` skill, which routes to `pdf-to-markdown`, `pymupdf-pdf`, `liteparse`, or `mineru`.
- **Routine page edits** (merge, split, rotate, crop, watermark, fill forms, redact) → `pymupdf` directly: `insert_pdf`, `set_toc`, `insert_textbox`, `show_pdf_page`, `apply_redactions`, widget field updates.

## Prerequisites — install check

Check what your task needs and install only what's missing — a missing tool is **not** an error unless your workflow reaches for it.

### Check

```bash
# Node.js >= 22 — required by Puppeteer 25.x
node --version

# JS packages — run from the project that will use them
for pkg in puppeteer @signpdf/signpdf; do
  npm ls --depth=0 "$pkg" >/dev/null 2>&1 && echo "$pkg: ok" || echo "$pkg: MISSING"
done

# CLI tools
for cmd in qpdf gs verapdf; do
  command -v "$cmd" >/dev/null 2>&1 && echo "$cmd: ok" || echo "$cmd: MISSING"
done
```

### Install

```bash
# JS — install into the project you're working in
npm i puppeteer                 # HTML→PDF; downloads its own Chromium
npm i @signpdf/signpdf @signpdf/signer-p12 @signpdf/placeholder-plain \
  @signpdf/utils                # digital signatures

# CLI — macOS
brew install qpdf ghostscript verapdf

# CLI — Debian/Ubuntu (verapdf is not packaged; download from docs.verapdf.org)
sudo apt install qpdf ghostscript
```

Puppeteer downloads its own Chromium at install — no separate Chrome needed. If the browser is missing (e.g. `PUPPETEER_SKIP_DOWNLOAD` was set), run `npx puppeteer browsers install chrome`.

## Quick Reference

| Task                       | Tool                          | Key Point                                                                  |
| -------------------------- | ----------------------------- | -------------------------------------------------------------------------- |
| Generate PDF from HTML     | Puppeteer / Playwright        | `page.pdf()`; settle fonts via `waitForNetworkIdle()` (Puppeteer) or `networkidle` (Playwright) |
| Tagged PDF (accessibility) | Puppeteer                     | `tagged: true` maps HTML semantics to PDF structure tags                   |
| PDF/A conversion           | ghostscript                   | `gs -dPDFA=2`; use PDF/A-2b for most archival needs                        |
| PDF/A / PDF/UA validation  | verapdf                       | `--flavour 2b` / `--flavour ua1`                                           |
| Digital signatures         | @signpdf/\*                   | PKCS#7 signing with P12 certificates                                       |
| Encrypt PDF                | qpdf                          | AES-256: `qpdf --encrypt user owner 256 --`                                |
| Repair corrupted PDF       | qpdf                          | `qpdf input.pdf --replace-input`                                           |
| Linearize (fast web view)  | qpdf                          | `qpdf --linearize input.pdf output.pdf`                                    |

## Common Mistakes

| Mistake                                                | Correct Pattern                                                   |
| ------------------------------------------------------ | ----------------------------------------------------------------- |
| Using canvas drawing commands for PDF generation       | Use Puppeteer/Playwright with HTML/CSS templates                  |
| Relying on `window.print()` for server-side generation | Use headless browser APIs (`page.pdf()`) for deterministic output |
| Skipping font embedding in containers                  | Embed Google Fonts or WOFF2 files with Puppeteer                  |
| Storing unencrypted PDFs with PII in public storage    | Apply AES-256 encryption via qpdf before storage                  |

## References

- [High-Fidelity Generation](references/high-fidelity-generation.md) -- Puppeteer HTML-to-PDF, CSS print tips, React templates, browser pooling
- [Security and Archival](references/security-and-archival.md) -- qpdf encrypt/repair/linearize, PDF/A via ghostscript + verapdf, tagged PDFs, @signpdf signing

## Self-Test

After changing SKILL.md or any reference, run the offline self-test. It checks structure (dead links, orphans), doc drift (deprecated API patterns, parse-docs routing consistency, the prerequisites Check block), and live-executes what's checkable offline (ghostscript). Missing deps SKIP with an install hint — they never fail:

```bash
python3 evals/selftest.py
```
