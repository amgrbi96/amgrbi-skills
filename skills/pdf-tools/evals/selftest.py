#!/usr/bin/env python3
"""Offline self-test for the pdf-tools skill — no network required.

Run after changing SKILL.md or any file under references/:

    python3 evals/selftest.py

Covers, in order:
1. Structure: SKILL.md reference links match the references/ directory
   (no dead links, no orphan files), frontmatter on every reference.
2. Doc drift: deprecated patterns are gone (`networkidle0`, `import fitz`,
   `scripts/*` invocations), the parse-docs routing note still matches the
   sibling skill, and the prerequisites Check block runs and reports every
   expected tool.
3. Examples: ghostscript round-trip (fixture built with gs itself) and, if
   qpdf is installed, encrypt/decrypt/linearize. Missing deps SKIP with an
   install hint; they never FAIL.

Puppeteer examples are deliberately not executed (Chromium download);
they are covered by the static drift checks only.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
SKILL_MD = SKILL_DIR / "SKILL.md"
PARSE_DOCS = SKILL_DIR.parent / "parsing" / "parse-docs" / "SKILL.md"

PASSED, FAILED, SKIPPED = [0], [0], [0]

EXPECTED_PREREQ_NAMES = {"puppeteer", "@signpdf/signpdf", "qpdf", "gs", "verapdf"}

ROUTING_TOOLS = ["pdf-to-markdown", "pymupdf-pdf", "liteparse", "mineru"]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print(f"PASS {name}")
    else:
        FAILED[0] += 1
        print(f"FAIL {name}" + (f" — {detail}" if detail else ""))


def skip(name, why):
    SKIPPED[0] += 1
    print(f"SKIP {name} — {why}")


def section(title):
    print(f"\n===== {title} =====")


# ---------------------------------------------------------------------------
# 1. Structure
# ---------------------------------------------------------------------------
def structure_tests():
    section("structure")

    linked = set(re.findall(r"references/([a-z0-9-]+\.md)", SKILL_MD.read_text()))
    on_disk = {p.name for p in REFS.glob("*.md")}
    check("structure: no dead reference links", linked <= on_disk,
          f"linked but missing: {sorted(linked - on_disk)}")
    check("structure: no orphan reference files", on_disk <= linked,
          f"on disk but not linked: {sorted(on_disk - linked)}")

    for md in REFS.glob("*.md"):
        head = md.read_text().split("---")
        ok = md.read_text().startswith("---\n") and len(head) > 2 \
            and "title:" in head[1] and "description:" in head[1]
        check(f"structure: frontmatter in {md.name}", ok)

    body_lines = len(SKILL_MD.read_text().splitlines())
    check("structure: SKILL.md body under 120 lines", body_lines < 120,
          f"{body_lines} lines")

    fm = SKILL_MD.read_text().split("---")[1]
    check("structure: SKILL.md name and version",
          "name: pdf-tools" in fm and re.search(r"version: '\d+\.\d+'", fm))


# ---------------------------------------------------------------------------
# 2. Doc drift
# ---------------------------------------------------------------------------
def drift_tests():
    section("doc drift")

    corpus = {p.name: p.read_text() for p in [SKILL_MD, *REFS.glob("*.md")]}

    check("drift: no networkidle0 anywhere",
          not any("networkidle0" in t for t in corpus.values()))
    check("drift: no deprecated 'import fitz'",
          not any(re.search(r"import fitz\b|\bfitz\.", t) for t in corpus.values()))
    check("drift: no scripts/ invocations",
          not any(re.search(r"python3? +scripts?/", t) for t in corpus.values()))

    for name, text in corpus.items():
        if "ignoreEncryption" in text:
            check(f"drift: ignoreEncryption warned in {name}",
                  "never decrypts" in text or "suppresses" in text.lower())

    if PARSE_DOCS.exists():
        pd = PARSE_DOCS.read_text()
        check("drift: routing targets exist in parse-docs",
              all(t in pd for t in ROUTING_TOOLS),
              f"missing: {[t for t in ROUTING_TOOLS if t not in pd]}")
        check("drift: SKILL.md routes extraction to parse-docs",
              "parse-docs" in corpus["SKILL.md"]
              and all(t in corpus["SKILL.md"] for t in ROUTING_TOOLS))
    else:
        skip("drift: parse-docs cross-check", "sibling skill not installed")


# ---------------------------------------------------------------------------
# 3. Prerequisites Check block (executed verbatim from SKILL.md)
# ---------------------------------------------------------------------------
def prereq_block_tests():
    section("prereq block")

    m = re.search(r"### Check\s+```bash\n(.*?)```", SKILL_MD.read_text(), re.S)
    if not m:
        check("prereq: Check block found in SKILL.md", False)
        return
    check("prereq: Check block found in SKILL.md", True)

    with tempfile.TemporaryDirectory(prefix="pdf-tools-prereq-") as td:
        script = Path(td) / "check.sh"
        script.write_text(m.group(1))
        proc = subprocess.run(["bash", str(script)], capture_output=True,
                              text=True, timeout=120)
        reported = dict(re.findall(r"^(\S+): (ok|MISSING)$", proc.stdout, re.M))
        check("prereq: check block exits 0", proc.returncode == 0,
              proc.stderr[:200])
        check("prereq: every expected tool reported",
              EXPECTED_PREREQ_NAMES <= set(reported),
              f"not reported: {sorted(EXPECTED_PREREQ_NAMES - set(reported))}")


# ---------------------------------------------------------------------------
# 4. Execute what's checkable offline
# ---------------------------------------------------------------------------
def example_tests():
    section("examples")

    gs = shutil.which("gs")
    qpdf = shutil.which("qpdf")

    with tempfile.TemporaryDirectory(prefix="pdf-tools-examples-") as td:
        tdp = Path(td)

        if gs:
            # fixture built with gs itself — no other PDF dependency needed
            r = subprocess.run(
                [gs, "-o", str(tdp / "input.pdf"), "-sDEVICE=pdfwrite",
                 "-c", "newpath 0 0 moveto 100 100 lineto stroke showpage"],
                capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0 and (tdp / "input.pdf").exists() \
                and (tdp / "input.pdf").read_bytes()[:5] == b"%PDF-"
            check("cli: gs builds a fixture PDF", ok, r.stderr[:200])

            # the documented PDF/A conversion command, verbatim shape
            r = subprocess.run(
                [gs, "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                 "-sColorConversionStrategy=UseDeviceIndependentColor",
                 f"-sOutputFile={tdp / 'output-pdfa.pdf'}",
                 str(tdp / "input.pdf")],
                capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0 and (tdp / "output-pdfa.pdf").exists()
            check("cli: gs PDF/A conversion produces a PDF", ok, r.stderr[:200])
        else:
            skip("cli: gs round-trip", "ghostscript not installed")

        if qpdf:
            r = subprocess.run(
                [qpdf, "--encrypt", "user", "owner", "256", "--",
                 str(tdp / "input.pdf"), str(tdp / "secured.pdf")],
                capture_output=True, text=True, timeout=60)
            check("cli: qpdf AES-256 encryption", r.returncode == 0,
                  r.stderr[:200])

            r = subprocess.run(
                [qpdf, "--password=user", "--decrypt",
                 str(tdp / "secured.pdf"), str(tdp / "decrypted.pdf")],
                capture_output=True, text=True, timeout=60)
            ok = r.returncode == 0 and (tdp / "decrypted.pdf").exists()
            check("cli: qpdf decrypt round-trip", ok, r.stderr[:200])

            r = subprocess.run(
                [qpdf, "--linearize", str(tdp / "input.pdf"),
                 str(tdp / "linearized.pdf")],
                capture_output=True, text=True, timeout=60)
            ok = r.returncode == 0 and (tdp / "linearized.pdf").exists()
            check("cli: qpdf linearization", ok, r.stderr[:200])
        else:
            skip("cli: qpdf encrypt/decrypt/linearize",
                 "qpdf not installed — brew install qpdf")


def main():
    structure_tests()
    drift_tests()
    prereq_block_tests()
    example_tests()
    total = PASSED[0] + FAILED[0]
    print(f"\n{'=' * 50}\n{PASSED[0]}/{total} passed, {FAILED[0]} failed, "
          f"{SKIPPED[0]} skipped")
    sys.exit(1 if FAILED[0] else 0)


if __name__ == "__main__":
    main()
