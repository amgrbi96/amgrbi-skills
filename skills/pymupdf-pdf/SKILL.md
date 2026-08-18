---
name: pymupdf-pdf
description: Fast local PDF parsing with PyMuPDF (fitz) for Markdown/JSON outputs and optional images/tables. Use when speed matters more than robustness, or as a fallback while heavier parsers are unavailable. Default to single-PDF parsing with per-document output folders.
metadata:
  openclaw:
    emoji: "📄"
    requires:
      bins: ["python3"]
    install:
      - id: pip
        kind: pip
        packages: ["pymupdf"]
        label: "Install PyMuPDF (pip)"
      - id: pip-optional
        kind: pip
        packages: ["pymupdf4llm"]
        label: "Optional: layout detection addon (pymupdf.layout)"
---

# PyMuPDF PDF

## Overview
Parse PDFs locally using PyMuPDF for fast, lightweight extraction into Markdown by default, with optional JSON and image/table outputs in a per-document directory.

## Setup

Prerequisites: `python3` + the `pymupdf` package. Nothing else — no cloud, no token, no other binaries. The script exits 1 with an install hint if PyMuPDF is missing (`--help` works without it).

1. Install PyMuPDF:

```bash
pip install pymupdf
```

If pip refuses with "externally-managed-environment" (macOS/Linux system Python), either use a venv:

```bash
python3 -m venv ~/.venvs/pymupdf
~/.venvs/pymupdf/bin/pip install pymupdf
# then invoke the script with that interpreter:
~/.venvs/pymupdf/bin/python3 scripts/pymupdf_parse.py /path/to/file.pdf
```

or force it: `pip install --break-system-packages pymupdf`.

2. Verify the dependency:

```bash
python3 -c "import pymupdf; print(pymupdf.__version__)"   # expect: 1.24.x or later
```

3. Smoke-test the script (validates dependency + a real PDF, writes nothing):

```bash
./scripts/pymupdf_parse.py /path/to/any.pdf --dry-run
# expect: "✅ Dry run OK — valid PDF, N pages. Ready to parse." (exit 0)
```

Troubleshooting: NixOS `libstdc++` import failures and other notes live in `references/pymupdf-notes.md`.

Optional — layout detection (`pymupdf.layout`, see below) additionally needs:

```bash
pip install pymupdf4llm
```

## Quick start (single PDF)
```bash
# Run from the skill directory
./scripts/pymupdf_parse.py /path/to/file.pdf \
  --format md \
  --outroot ./pymupdf-output
```

Always validate first — checks the file and opens the PDF without writing anything:

```bash
./scripts/pymupdf_parse.py /path/to/file.pdf --dry-run
```

## Options
- `--format md|json|both` (default: `md`)
- `--images` to extract images
- `--tables` to extract a simple line-based table JSON (quick/rough)
- `--outroot DIR` to change output root (default: `./pymupdf-output`)
- `--lang` adds a language hint into JSON output metadata (default: `en`)
- `--dry-run` to validate the input PDF and exit without writing anything

## Error handling
- Pre-flight checks reject: missing file, non-PDF extension, empty file, corrupt PDF, password-protected PDF — each with a one-line error
- Missing PyMuPDF exits with a clear install hint (`pip install pymupdf`); `--help` works without the dependency
- Exit code 0 only on success (or dry-run OK); 1 on invalid input, missing dependency, or parse failure — safe for scripting
- A JSON summary block (file, pages, outputs, elapsed) prints at the end

## Output conventions
- Create `./pymupdf-output/<pdf-stem>/` by default (filename without extension).
- Markdown output: `output.md` (with `<!-- page N -->` markers per page)
- JSON output: `output.json` (includes `lang`)
- Images: `images/` subdir (`page-N-img-M.png`)
- Tables: `tables.json` (rough line-based)

## Layout Detection (pymupdf.layout addon)

Detect tables, images, headers with bounding boxes — local, GNN-based, no cloud needed.

### Setup

```bash
pip install pymupdf pymupdf4llm --break-system-packages
```

### API

```python
import pymupdf4llm
import pymupdf.layout as layout_mod
import json

layout_mod.activate()  # MUST call before to_json()

raw = pymupdf4llm.to_json("document.pdf", pages=[0,1,2])
result = json.loads(raw)  # returns JSON string, parse it

for page_data in result["pages"]:
    page_num = page_data["page_number"]
    for box in page_data.get("boxes", []):
        print(box["boxclass"])  # "table", "image", "section-header", "page-header", "text"
        print(box["x0"], box["y0"], box["x1"], box["y1"])  # PDF-native coordinates
```

### Box classes

| `boxclass` | Meaning |
|---|---|
| `table` | Detected table region |
| `image` | Embedded image/figure |
| `section-header` | Section or column header |
| `page-header` | Running header/footer |
| `text` | General text block |

### Crop a detected table to PNG

```python
import pymupdf, io
from PIL import Image

doc = pymupdf.open("document.pdf")
page = doc[page_num - 1]
mat = pymupdf.Matrix(300/72, 300/72)  # 300 DPI
pix = page.get_pixmap(matrix=mat, clip=pymupdf.Rect(x0, y0, x1, y1))
img = Image.open(io.BytesIO(pix.tobytes("png")))
img.save("table.png")
```

### Critical notes

- **Import**: `import pymupdf.layout` (NOT `import pymupdf_layout`)
- **Activation**: Must call `layout_mod.activate()` before `pymupdf4llm.to_json()` to populate `boxes`
- **to_json() returns a string**: Must `json.loads()` it
- **Page numbers**: 1-indexed in `page_number` field; `doc[page_num - 1]` for PyMuPDF access
- **Landscape pages**: PyMuPDF handles rotation automatically via `get_pixmap(clip=...)`
- **Padding**: Add ~8px padding around bboxes for cleaner crops

### When to use

| Need | Tool |
|---|---|
| Block-level layout detection (tables, images, headers) | `pymupdf.layout` |
| Crop table/figure images from PDF | `pymupdf.layout` bboxes → `get_pixmap(clip=...)` |
| Fast text extraction | PyMuPDF `page.get_text()` |
| Higher accuracy layout with formula recognition | MinerU (cloud VLM) |

## Notes
- PyMuPDF is fast but less robust on complex PDFs.
- For more robust parsing, use a heavy-duty OCR parser (e.g., MinerU) if installed.
- `pymupdf.layout` gives block-level bboxes locally (GNN-based) — good alternative to MinerU cloud when layout detection is needed without cloud dependency.
