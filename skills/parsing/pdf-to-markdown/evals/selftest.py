#!/usr/bin/env python3
"""Self-test for the pdf-to-markdown skill.

    python3 skills/parsing/pdf-to-markdown/evals/selftest.py

Run after changing bin/ wrappers or any documented claim in SKILL.md.
Covers, in order:
1. Wrapper tests (no binary needed): check-env usage gate, platform
   rejection via a fake uname shim, wrapper executability.
2. Binary tests (cached binary, isolated HOME): conversion behaviors and
   exit codes verified during the Aug 2026 audit — text/scanned/encrypted
   fixtures, batch partial failure, image export, pdf-to-text, query,
   the --vision license gate, and the 3-arg silent-ignore trap.
   SKIPs cleanly when the binary or pymupdf is unavailable.
3. Doc drift: SKILL.md flag block vs `pdf-to-markdown --help`, verified
   stamps present, check-env documented, body size.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
WRAPPER = SKILL_DIR / "bin" / "pdf-to-markdown"
CHECK_ENV = SKILL_DIR / "bin" / "check-env"
SKILL_MD = SKILL_DIR / "SKILL.md"
STATE_DIR = Path.home() / ".local" / "share" / "nutrient"

PASSED, FAILED, SKIPPED = [0], [0], [0]

# --license-key is real but intentionally absent from --help (documented
# as such in SKILL.md), so the drift check must not flag it.
HIDDEN_BUT_DOCUMENTED = {"license-key"}


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


def run(cmd, env=None, timeout=120):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       env=env, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


# ---------------------------------------------------------------------------
# Tier 1: wrapper logic, no binary involved
# ---------------------------------------------------------------------------
def wrapper_tests():
    section("wrapper (no binary)")
    check("wrapper: script present + executable",
          WRAPPER.is_file() and os.access(WRAPPER, os.X_OK))
    check("wrapper: check-env present + executable",
          CHECK_ENV.is_file() and os.access(CHECK_ENV, os.X_OK))
    check("wrapper: wrapper is POSIX sh (downloads binary, not bundled)",
          WRAPPER.read_text().startswith("#!/bin/sh")
          and "agent-cdn.nutrient.io" in WRAPPER.read_text())

    code, _, err = run([CHECK_ENV, "--bogus"])
    check("check-env: bad arg -> 2 + usage", code == 2 and "usage" in err,
          f"code={code} err={err!r}")

    # fake uname shim -> platform rejection before any network access
    tdir = Path(tempfile.mkdtemp(prefix="ptm-wrap-"))
    shim = tdir / "bin"
    shim.mkdir()
    (shim / "uname").write_text(
        '#!/bin/sh\ncase "$1" in -m) echo i386;; *) echo Darwin;; esac\n')
    (shim / "uname").chmod((shim / "uname").stat().st_mode | stat.S_IEXEC)
    home = tdir / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), PATH=f"{shim}:{os.environ['PATH']}")

    code, _, err = run([WRAPPER], env=env)
    check("wrapper: Intel Mac rejected -> 1", code == 1 and "Unsupported platform" in err,
          f"code={code} err={err!r}")
    code, so, err = run([CHECK_ENV], env=env)
    check("check-env: Intel Mac rejected -> 1",
          code == 1 and "unsupported platform" in (so + err).lower(),
          f"code={code} out={so!r} err={err!r}")

    shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tier 2: real binary, isolated HOME pointing at the cached install
# ---------------------------------------------------------------------------
def isolated_env(home):
    """HOME is redirected but the installed binary is reused via a symlink,
    and a fresh state file keeps the wrapper from phoning the CDN."""
    nut = home / ".local" / "share" / "nutrient"
    nut.mkdir(parents=True)
    real_cli = next(STATE_DIR.glob("cli/nutrient-*"), None)
    if real_cli is None:
        return None
    (nut / "cli").symlink_to(real_cli.resolve().parent, target_is_directory=True)
    release = ""
    real_state = STATE_DIR / "pdf-to-markdown-state"
    if real_state.is_file():
        release = re.search(r"RELEASE_ID=(\S+)", real_state.read_text())
        release = release.group(1) if release else ""
    (nut / "pdf-to-markdown-state").write_text(
        f"LAST_CHECKED_AT={int(time.time())}\nRELEASE_ID={release}\n")
    return dict(os.environ, HOME=str(home))


def binary_tests():
    section("binary (isolated HOME)")
    tdir = Path(tempfile.mkdtemp(prefix="ptm-bin-"))
    home = tdir / "home"
    home.mkdir()
    env = isolated_env(home)
    if env is None:
        skip("binary", "no installed binary; run bin/check-env --install first")
        return dict(binary_available=False, env=None, tdir=tdir)

    W = [WRAPPER]
    out = tdir / "out"
    out.mkdir()

    code, so, se = run(W + ["--help"], env=env)
    check("cli: top-level --help -> 0 + subcommands",
          code == 0 and all(c in so for c in ("pdf-to-markdown", "pdf-to-text", "query")))
    code, so, se = run(W + ["pdf-to-markdown", "--help"], env=env)
    check("cli: subcommand --help -> 0", code == 0 and "pdf-to-markdown" in so)
    for flag in ("--enable-image-export", "--vision", "--provider"):
        check(f"cli: help lists {flag}", flag in so + se)
    code, so, _ = run(W + ["--version"], env=env)
    check("cli: --version -> 0 + semver", code == 0 and re.search(r"\d+\.\d+", so), so)

    # error paths that need no fixtures
    code, _, se = run(W + ["missing.pdf", str(out / "x.md")], env=env)
    check("cli: missing input -> 1", code == 1 and "failed to open document" in se, se)
    (tdir / "notpdf.txt").write_text("hello")
    code, _, se = run(W + [tdir / "notpdf.txt", str(out / "x.md")], env=env)
    check("cli: non-PDF -> 1", code == 1 and "failed to open document" in se, se)
    code, _, se = run(W + ["doc.pdf", str(tdir / "nodir" / "x.md")], env=env)
    check("cli: missing outdir -> 1", code == 1 and "does not exist" in se, se)

    # fixtures need pymupdf
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        skip("fixtures", "pymupdf not installed (pip install pymupdf)")
        shutil.rmtree(tdir, ignore_errors=True)
        return dict(binary_available=True, env=None, tdir=None)

    make_fixtures(tdir)
    text_pdf, scanned_pdf, enc_pdf = tdir / "text.pdf", tdir / "scanned.pdf", tdir / "enc.pdf"

    md = out / "text.md"
    code, _, se = run(W + [text_pdf, md], env=env)
    body = md.read_text() if md.exists() else ""
    check("convert: text PDF -> 0 + non-empty", code == 0 and len(body) > 100, se)
    check("convert: H1 heading", "# Quarterly Report" in body)
    check("convert: table as HTML", "<table>" in body and "<td>Q1</td>" in body)
    check("convert: list items", "- Revenue up 12 percent" in body)

    code, so, _ = run(W + [text_pdf], env=env)
    check("convert: stdout mode matches file mode", code == 0 and so == body)

    md2 = out / "text2.md"
    code, _, _ = run(W + [text_pdf, md2, tdir / "ignored-arg"], env=env)
    check("trap: 3 args -> 0, arg3 silently ignored",
          code == 0 and md2.exists() and md2.read_text() == body
          and not (tdir / "ignored-arg").exists())

    smd = out / "scanned.md"
    code, _, _ = run(W + [scanned_pdf, smd], env=env)
    check("trap: scanned PDF -> exit 0 with ~empty output",
          code == 0 and smd.exists() and len(smd.read_text().strip()) == 0,
          f"code={code} size={smd.stat().st_size if smd.exists() else 'none'}")

    code, _, se = run(W + ["--vision", scanned_pdf, out / "v.md"], env=env)
    check("gate: --vision free tier -> 1 + error 3017",
          code == 1 and "3017" in se, f"code={code} err={se!r}")
    code, _, se = run(W + ["--vision", "--license-key", "invalid", scanned_pdf, out / "v2.md"],
                      env=env)
    check("gate: invalid --license-key rejected", code != 0 and "license" in se.lower(), se)

    emd = out / "enc.md"
    code, _, se = run(W + [enc_pdf, emd], env=env)
    check("cli: encrypted -> 1 + 0-byte output left behind",
          code == 1 and "Unencrypted" in se and emd.exists() and emd.stat().st_size == 0, se)

    # batch with mixed quality
    bin_, bout = tdir / "batch-in", out / "batch"
    bin_.mkdir()
    shutil.copy(text_pdf, bin_ / "text.pdf")
    shutil.copy(tdir / "corrupt.pdf", bin_ / "corrupt.pdf")
    shutil.copy(tdir / "notpdf.txt", bin_ / "notes.txt")
    code, _, se = run(W + [bin_, bout], env=env)
    check("batch: partial failure -> 1 + summary",
          code == 1 and "2 of 3 files failed" in se, se)
    check("batch: successes still written", (bout / "text.md").exists())

    # image export
    imd = out / "img.md"
    code, _, _ = run(W + ["--enable-image-export", scanned_pdf, imd], env=env)
    imgs = list((out / "img_resources").glob("image_*.jpeg")) if (out / "img_resources").exists() else []
    check("images: exported to {output}_resources/", code == 0 and len(imgs) >= 1)
    check("images: referenced with literal Description alt",
          "![Description](img_resources/" in imd.read_text())

    # companion subcommands
    code, so, _ = run(W + ["pdf-to-text", text_pdf], env=env)
    check("pdf-to-text: layout-preserving table", code == 0 and re.search(r"Quarter\s+Revenue", so))

    # query: attribution + json "document" key only appear for multi-file corpora
    shutil.copy(bout / "text.md", bout / "text2.md")
    code, so, _ = run(W + ["query", "text", bout, "revenue", "-k", "2"], env=env)
    check("query: ranked hits over multi-file directory",
          code == 0 and "text.md" in so and "Revenue" in so, so[:200])
    idx = out / "q.idx"
    code, _, _ = run(W + ["query", "text", bout, "revenue", "--emit-index", idx], env=env)
    ok_idx = code == 0 and idx.exists() and idx.stat().st_size > 0
    code, so, _ = run(W + ["query", "text", idx, "churn", "-k", "1", "--display", "json"], env=env)
    parsed = False
    if ok_idx and so.strip().startswith("["):
        hits = json.loads(so)
        parsed = bool(hits) and all(k in hits[0] for k in ("line", "score", "text"))
    check("query: index build + reuse + json output", ok_idx and code == 0 and parsed,
          f"idx={ok_idx} code={code} out={so[:120]!r}")
    code, so, _ = run(W + ["query", "text", bout, "churn", "-k", "1", "--display", "json"], env=env)
    doc_key = bool(so.strip()) and "document" in json.loads(so)[0]
    check("query: directory json includes document attribution", code == 0 and doc_key, so[:120])

    return dict(binary_available=True, env=env, tdir=tdir)


def make_fixtures(tdir):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    y = 72

    def put(t, size=11, font="helv"):
        nonlocal y
        page.insert_text((72, y), t, fontsize=size, fontname=font)
        y += size * 1.6

    put("Quarterly Report", 24, "hebo")
    put("Overview", 16, "hebo")
    put("Revenue grew 12% year over year. Costs were flat.")
    put("- Revenue up 12 percent")
    put("- Churn down 3 points")
    put("Numbers", 16, "hebo")
    ty = y
    for row in (["Quarter", "Revenue", "Cost"], ["Q1", "100", "40"],
                ["Q2", "112", "41"], ["Q3", "118", "39"]):
        tx = 72
        for cell in row:
            page.insert_text((tx, ty), cell, fontsize=10)
            tx += 110
        ty += 16
    doc.save(tdir / "text.pdf")

    pix = pymupdf.open(tdir / "text.pdf")[0].get_pixmap(dpi=150)
    scanned = pymupdf.open()
    pg = scanned.new_page(width=612, height=792)
    pg.insert_image(pymupdf.Rect(0, 0, 612, 792), pixmap=pix)
    scanned.save(tdir / "scanned.pdf")  # image-only: no text layer

    pymupdf.open(tdir / "text.pdf").save(
        tdir / "enc.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret", owner_pw="owner")

    (tdir / "corrupt.pdf").write_bytes((tdir / "text.pdf").read_bytes()[:100])


# ---------------------------------------------------------------------------
# Tier 3: doc drift — SKILL.md claims vs the binary's --help
# ---------------------------------------------------------------------------
def drift_tests(ctx):
    section("doc drift")
    text = SKILL_MD.read_text()

    stamps = re.findall(r"verified[^\n]{0,40}20\d\d", text, re.IGNORECASE)
    check("drift: SKILL.md has verified stamps", len(stamps) >= 2, str(stamps))
    check("drift: check-env documented", "check-env" in text)
    check("drift: routing table present", "mineru" in text and "liteparse" in text)
    lines = len(text.splitlines())
    check("drift: SKILL.md body under 200 lines", lines < 200, f"{lines} lines")

    doc_flags = {f.lstrip("-") for f in re.findall(r"^(--[a-z-]+)", text, re.MULTILINE)} - {""}
    if not ctx["binary_available"]:
        skip("drift: flags vs --help", "no binary installed")
        return
    code, so, _ = run([WRAPPER, "pdf-to-markdown", "--help"], env=ctx["env"])
    help_flags = set(re.findall(r"--([a-z][a-z-]+)", so)) - {"help"}
    if code != 0:
        skip("drift: flags vs --help", f"--help exited {code}")
        return
    missing = doc_flags - HIDDEN_BUT_DOCUMENTED - help_flags
    check("drift: documented flags exist in --help", not missing, f"missing: {sorted(missing)}")
    undocumented = help_flags - doc_flags - HIDDEN_BUT_DOCUMENTED
    check("drift: help flags documented in SKILL.md", not undocumented,
          f"undocumented: {sorted(undocumented)}")


def main():
    wrapper_tests()
    ctx = binary_tests()
    drift_tests(ctx)
    total = PASSED[0] + FAILED[0]
    print(f"\n{'=' * 50}\n{PASSED[0]}/{total} passed, {FAILED[0]} failed, {SKIPPED[0]} skipped")
    sys.exit(1 if FAILED[0] else 0)


if __name__ == "__main__":
    main()
