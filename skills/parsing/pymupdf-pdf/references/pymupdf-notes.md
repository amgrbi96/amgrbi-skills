# PyMuPDF Notes

- Fast local parsing via PyMuPDF — `import pymupdf` (canonical since 1.24; the old `import fitz` name is deprecated and the script only uses it as a fallback for older installs).
- Requires PyMuPDF ≥ 1.23 for native table extraction (`page.find_tables()`); older installs fall back to line-based table output.
- `page.get_text("markdown")` gives quick Markdown output.
- `page.get_text("text")` provides plain text for JSON.
- Image extraction uses `page.get_images(full=True)` and `Pixmap`.

Install:
```bash
pip install "pymupdf>=1.23"
```

If pip refuses ("externally-managed-environment" on macOS/Linux system Python):

```bash
# option A: dedicated venv (recommended)
python3 -m venv ~/.venvs/pymupdf
~/.venvs/pymupdf/bin/pip install pymupdf

# option B: force system-wide
pip install --break-system-packages pymupdf
```

Verify:
```bash
python3 -c "import pymupdf; print(pymupdf.__version__)"   # expect 1.23+
```

Nix note (if `import pymupdf` fails with libstdc++ missing):
```bash
# Find a gcc lib path and export it:
ls /nix/store/*gcc*/lib/libstdc++.so.6 2>/dev/null | head -1
export LD_LIBRARY_PATH=/nix/store/<your-gcc-lib-hash>-gcc-<version>-lib/lib
```
