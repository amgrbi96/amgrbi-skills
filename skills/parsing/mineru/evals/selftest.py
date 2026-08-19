#!/usr/bin/env python3
"""Offline self-test for the mineru skill — no network, no real tokens.

Run after changing scripts/mineru_v2.py or any documented claim in SKILL.md:

    python3 evals/selftest.py

Covers, in order:
1. Unit tests (mocked): token-pool state/rotation, process_file flows, waste
   guards, --check-token verdicts.
2. CLI tests (subprocess, isolated HOME): arg validation, exit codes, dry-run,
   resume, state-file behavior, missing-dependency handling.
3. Doc drift: SKILL.md's CLI table vs the script's --help (flags + defaults),
   verified-stamps present, body under 500 lines.

Usage: selftest.py [--skill-md PATH]   (PATH overrides SKILL.md for drift checks)
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import random
import zipfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "scripts" / "mineru_v2.py"
DEFAULT_SKILL_MD = SKILL_DIR / "SKILL.md"
API_REF = SKILL_DIR / "references" / "api_reference.md"

PASSED, FAILED = [0], [0]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print(f"PASS {name}")
    else:
        FAILED[0] += 1
        print(f"FAIL {name}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n===== {title} =====")


# ---------------------------------------------------------------------------
# Unit tests (module import, fully mocked network)
# ---------------------------------------------------------------------------
def unit_tests():
    section("unit (mocked)")
    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    import mineru_v2 as m

    tdir = Path(tempfile.mkdtemp(prefix="mineru-unit-"))
    m.STATE_DIR = tdir / "state"
    m.STATE_FILE = m.STATE_DIR / "state.json"
    today = date.today().isoformat()

    def opts(**kw):
        base = dict(model="vlm", language="auto", no_formula=False, no_table=False,
                    pages=None, extra_formats_list=[])
        base.update(kw)
        return SimpleNamespace(**base)

    # --- token pool: rotation, exhaustion, dead, persistence, date reset ---
    toks = [f"tok{i}-aaaaaaaaaaaaaaaaaaaa" for i in range(6)]
    pool = m.TokenPool(toks)
    check("pool: fresh state, all active", sorted(pool.available()) == sorted(toks))
    check("pool: round-robin covers all", sorted(pool.next() for _ in range(6)) == sorted(toks))
    pool.mark_exhausted(toks[0])
    pool.mark_dead(toks[1], "test")
    check("pool: unavailable excluded", toks[0] not in pool.available() and toks[1] not in pool.available())
    pool.save_state()
    state = json.loads(m.STATE_FILE.read_text())
    check("pool: state persisted", state.get(pool._key(toks[0])) == {"exhausted": today}
          and state.get(pool._key(toks[1])) == {"dead": True}, str(state))
    pool2 = m.TokenPool(toks)
    check("pool: reload keeps exhausted+dead",
          toks[0] not in pool2.available() and toks[1] not in pool2.available())
    state[pool._key(toks[0])] = {"exhausted": (date.today() - timedelta(days=1)).isoformat()}
    m.STATE_FILE.write_text(json.dumps(state))
    pool3 = m.TokenPool(toks)
    check("pool: stale date resets", toks[0] in pool3.available() and toks[1] not in pool3.available())
    pool4 = m.TokenPool(toks)
    pool4.mark_exhausted(toks[2])
    pool4.mark_dead(toks[3], "x")
    check("pool: next() skips unavailable",
          all(pool4.next() not in (toks[2], toks[3]) for _ in range(20)))
    pool4.revive(toks[3])
    check("pool: revive clears dead", toks[3] in pool4.available())

    # --- thread safety smoke ---
    pool_t = m.TokenPool(toks)
    errors = []

    def hammer():
        try:
            for _ in range(300):
                t = pool_t.next()
                if t is None:
                    break
                if random.random() < 0.02:
                    pool_t.mark_exhausted(t)
                if random.random() < 0.01:
                    pool_t.mark_dead(t, "x")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=hammer) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("pool: thread safety", not errors and not (set(pool_t.available()) & pool_t.dead))

    # --- process_file fixtures ---
    src = tdir / "in"
    src.mkdir()
    (src / "doc.pdf").write_bytes(b"%PDF-1.4 fake")
    (src / "bad.pdf").write_bytes(b"%PDF-1.4 fake")
    (src / "big.pdf").write_bytes(b"%PDF-1.4 fake")
    out_dir = tdir / "out"
    out_dir.mkdir()

    def ok_api(token, method, url, **kw):
        if "file-urls/batch" in url:
            return {"data": {"batch_id": "b1", "file_urls": ["http://oss/fake"]}}
        if "extract-results" in url:
            return {"data": {"extract_result": [{"state": "done", "full_zip_url": "http://zip"}]}}
        raise AssertionError(f"unexpected url {url}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("full.md", "# hello")
        zf.writestr("images/x.png", "png")
        zf.writestr("content.json", "{}")
    fake_get = mock.MagicMock(return_value=mock.MagicMock(content=buf.getvalue()))
    fake_put = mock.MagicMock(return_value=mock.MagicMock(status_code=200))

    # --- process_file: rotation on -60018 then A0202, then success ---
    def rotate_api(token, method, url, **kw):
        if "file-urls/batch" in url:
            if token.startswith("tok0"):
                raise m.APIError("-60018", "daily limit reached")
            if token.startswith("tok1"):
                raise m.APIError("A0202", "invalid token")
            return {"data": {"batch_id": "b1", "file_urls": ["http://oss/fake"]}}
        if "extract-results" in url:
            return {"data": {"extract_result": [{"state": "done", "full_zip_url": "http://zip"}]}}
        raise AssertionError(f"unexpected url {url}")

    pool5 = m.TokenPool(toks)
    with mock.patch.object(m, "api_call", rotate_api), \
         mock.patch.object(m, "requests", mock.MagicMock(get=fake_get, put=fake_put)):
        ok, stem, err = m.process_file(pool5, src / "doc.pdf", out_dir, 0, 1, opts())
    check("parse: rotation + zip extract + rename",
          ok and stem == "doc" and err is None
          and (out_dir / "doc" / "doc.md").exists()
          and (out_dir / "doc" / "images" / "x.png").exists()
          and not (out_dir / "doc.zip").exists(), f"{ok} {stem} {err}")
    check("parse: rotation marked pool",
          toks[0] in pool5.exhausted and toks[1] in pool5.dead)

    # --- process_file: payload reflects opts (pages, extra formats, language) ---
    captured = {}

    def cap_api(token, method, url, **kw):
        if "file-urls/batch" in url:
            captured["payload"] = kw["json"]
            return {"data": {"batch_id": "b1", "file_urls": ["http://oss/fake"]}}
        if "extract-results" in url:
            return {"data": {"extract_result": [{"state": "done", "full_zip_url": "http://zip"}]}}
        raise AssertionError(url)

    (src / "pay.pdf").write_bytes(b"%PDF-1.4 fake")
    pool5b = m.TokenPool(toks)
    with mock.patch.object(m, "api_call", cap_api), \
         mock.patch.object(m, "requests", mock.MagicMock(get=fake_get, put=fake_put)):
        m.process_file(pool5b, src / "pay.pdf", out_dir, 0, 1,
                       opts(pages="5-9", extra_formats_list=["docx", "html"],
                            model="pipeline", language="ch", no_table=True))
    p = captured["payload"]
    check("payload: pages/formats/model/language/no-table",
          p.get("page_ranges") == "5-9"
          and p.get("extra_formats") == ["docx", "html"]
          and p.get("model_version") == "pipeline"
          and p.get("language") == "ch"
          and p.get("enable_table") is False, json.dumps(p))

    (src / "def.pdf").write_bytes(b"%PDF-1.4 fake")
    captured.clear()
    with mock.patch.object(m, "api_call", cap_api), \
         mock.patch.object(m, "requests", mock.MagicMock(get=fake_get, put=fake_put)):
        m.process_file(m.TokenPool(toks), src / "def.pdf", out_dir, 0, 1, opts())
    p = captured["payload"]
    check("payload: defaults omit optional keys",
          "language" not in p and "page_ranges" not in p and "extra_formats" not in p
          and p.get("enable_formula") is True, json.dumps(p))

    # --- process_file: fatal -60006 no retry + --pages hint ---
    n = {"batch": 0}

    def fatal_api(token, method, url, **kw):
        if "file-urls/batch" in url:
            n["batch"] += 1
            raise m.APIError("-60006", "too many pages")
        raise AssertionError(url)

    with mock.patch.object(m, "api_call", fatal_api), mock.patch.object(m, "requests", mock.MagicMock()):
        ok, stem, err = m.process_file(m.TokenPool(toks), src / "big.pdf", out_dir, 0, 1, opts())
    check("fatal: -60006 no-retry + --pages hint",
          not ok and "-60006" in str(err) and "--pages" in str(err) and n["batch"] == 1,
          f"{ok} {err} calls={n['batch']}")

    # --- process_file: corrupt zip (HTML error page) -> 5 attempts, clean failure ---
    garbage_get = mock.MagicMock(return_value=mock.MagicMock(content=b"<html>error</html>"))
    with mock.patch.object(m, "api_call", ok_api), \
         mock.patch.object(m, "requests", mock.MagicMock(get=garbage_get, put=fake_put)), \
         mock.patch.object(m.time, "sleep", lambda *_: None):
        ok, stem, err = m.process_file(m.TokenPool(toks), src / "bad.pdf", out_dir, 0, 1, opts())
    check("zip: corrupt download -> clean failure after 5 attempts",
          not ok and "zip" in str(err).lower() and garbage_get.call_count == 5,
          f"{ok} {err} attempts={garbage_get.call_count}")

    # --- process_file: existing output short-circuits, no network ---
    with mock.patch.object(m, "api_call", ok_api), mock.patch.object(m, "requests", mock.MagicMock()) as freq:
        ok, stem, err = m.process_file(m.TokenPool(toks), src / "doc.pdf", out_dir, 0, 1, opts())
    check("resume: existing output skips without network", ok and not freq.get.called)

    # --- --pages chunks: per-range output dirs, no silent skip, idempotent ---
    (src / "chunk.pdf").write_bytes(b"%PDF-1.4 fake")
    chunk_out = tdir / "chunks"
    chunk_out.mkdir()
    with mock.patch.object(m, "api_call", ok_api), \
         mock.patch.object(m, "requests", mock.MagicMock(get=fake_get, put=fake_put)):
        ok1, _, _ = m.process_file(m.TokenPool(toks), src / "chunk.pdf", chunk_out, 0, 1, opts(pages="201-400"))
        ok2, _, _ = m.process_file(m.TokenPool(toks), src / "chunk.pdf", chunk_out, 0, 1, opts(pages="401-500"))
    check("chunks: each range gets its own output dir",
          ok1 and ok2
          and (chunk_out / "chunk-201-400" / "chunk-201-400.md").exists()
          and (chunk_out / "chunk-401-500" / "chunk-401-500.md").exists(),
          f"ok1={ok1} ok2={ok2}")
    with mock.patch.object(m, "api_call", ok_api), mock.patch.object(m, "requests", mock.MagicMock()) as freq:
        ok3, _, _ = m.process_file(m.TokenPool(toks), src / "chunk.pdf", chunk_out, 0, 1, opts(pages="201-400"))
    check("chunks: re-run of same range skips (idempotent)", ok3 and not freq.get.called)
    with mock.patch.object(m, "api_call", ok_api), \
         mock.patch.object(m, "requests", mock.MagicMock(get=fake_get, put=fake_put)):
        ok4, _, _ = m.process_file(m.TokenPool(toks), src / "chunk.pdf", chunk_out, 0, 1, opts())
    check("chunks: full-file run still writes plain dir",
          ok4 and (chunk_out / "chunk" / "chunk.md").exists())
    check("chunks: naming (ranges sanitized, probe exempt)",
          m.out_stem_for("book", opts(pages="1-10,15")) == "book-1-10_15"
          and m.out_stem_for("book", SimpleNamespace(pages="1-3", is_probe=True)) == "book"
          and m.out_stem_for("book", opts()) == "book")

    # --- waste guards: pdf_precheck_warnings ---
    guard_dir = tdir / "guards"
    guard_dir.mkdir()
    (guard_dir / "digital.pdf").write_bytes(b"%PDF-1.4 /Font /Helvetica /Count 30")
    (guard_dir / "scanned.pdf").write_bytes(b"%PDF-1.4 /Image /XObject /Count 30")
    (guard_dir / "huge.pdf").write_bytes(b"%PDF-1.4 /Image /Count 2500")
    (guard_dir / "photo.jpg").write_bytes(b"\xff\xd8 jpg")
    (guard_dir / "unreadable.pdf").mkdir()  # read_bytes raises -> skipped silently

    warns = m.pdf_precheck_warnings(
        sorted(guard_dir.iterdir()), m.TokenPool([toks[0]]))
    check("guards: text-layer warning", any("text layer detected" in w and "digital.pdf" in w for w in warns),
          str(warns))
    check("guards: no false text-layer on scanned", not any("scanned.pdf" in w and "text layer" in w for w in warns))
    check("guards: over-200 warning", any("huge.pdf" in w and "200-page" in w for w in warns))
    check("guards: budget warning when over capacity (30+30+2500 > 1000)",
          any("pages/day pool capacity" in w for w in warns), str(warns))
    check("guards: unreadable + non-pdf skipped silently",
          not any("unreadable" in w or "photo" in w for w in warns))
    small = [guard_dir / "digital.pdf"]  # 30 pages < 1000 capacity
    check("guards: no budget warning under capacity",
          not any("capacity" in w for w in m.pdf_precheck_warnings(small, m.TokenPool([toks[0]]))))
    deadpool = m.TokenPool([toks[0]])
    deadpool.mark_dead(toks[0], "x")
    check("guards: zero active tokens -> no budget warning",
          not any("capacity" in w for w in m.pdf_precheck_warnings([guard_dir / "huge.pdf"], deadpool)))

    # --- run_check_token verdicts ---
    def ct_api(token, method, url, **kw):
        assert "extract/task/selftest-probe" in url, url
        if token.startswith("bad"):
            raise m.APIError("A0202", "invalid token")
        if token.startswith("odd"):
            raise m.APIError("-1", "weird")
        raise m.APIError("-60012", "task not found")

    good, bad, odd = "good-token-aaaaaaaaaaaaaa", "bad-token-bbbbbbbbbbbbbb", "odd-token-cccccccccccccc"
    # pre-seed: good marked dead (stale) -> should be revived
    seed = {m.TokenPool([good])._key(good): {"dead": True}}
    m.STATE_FILE.write_text(json.dumps(seed))

    def isolated_env(tokens_csv=None):
        # strip real MINERU_TOKEN/MINERU_TOKENS from the user's shell so tests
        # can't inherit live tokens (patch.dict alone only merges/overrides)
        env = {k: v for k, v in os.environ.items() if k not in ("MINERU_TOKEN", "MINERU_TOKENS")}
        if tokens_csv:
            env["MINERU_TOKENS"] = tokens_csv
        return env

    no_file = tdir / "no-tokens.txt"  # exists but empty: blocks the skill's real tokens.txt without tripping the missing-file check
    no_file.touch()
    ct_args = SimpleNamespace(token=None, tokens_file=str(no_file))
    with mock.patch.object(m, "api_call", ct_api), \
         mock.patch.dict(os.environ, isolated_env(f"{good},{bad},{odd}"), clear=True):
        rc = m.run_check_token(ct_args)
    state = json.loads(m.STATE_FILE.read_text())
    kp = m.TokenPool([good, bad, odd])
    check("check-token: exit 0 while some active", rc == 0)
    check("check-token: invalid marked dead in state", state.get(kp._key(bad)) == {"dead": True}, str(state))
    check("check-token: stale-dead token revived", kp._key(good) not in state, str(state))
    with mock.patch.object(m, "api_call", ct_api), \
         mock.patch.dict(os.environ, isolated_env(bad), clear=True):
        rc = m.run_check_token(SimpleNamespace(token=None, tokens_file=str(no_file)))
    check("check-token: exit 1 when none active", rc == 1)

    shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI tests (subprocess, isolated HOME, fake tokens, no network)
# ---------------------------------------------------------------------------
def cli_tests():
    section("cli (offline)")
    tdir = Path(tempfile.mkdtemp(prefix="mineru-cli-"))
    home = tdir / "home"
    home.mkdir()
    (tdir / "in").mkdir()
    (tdir / "in" / "good.pdf").write_bytes(b"%PDF-1.4 fake")
    (tdir / "in" / "notes.txt").write_bytes(b"not a pdf")
    (tdir / "in" / ".DS_Store").write_bytes(b"junk")
    (tdir / "other.pdf").write_bytes(b"%PDF-1.4 fake")
    (tdir / "doc.docx").write_bytes(b"PK fake")
    tok = "fake-token-1234567890"
    (tdir / "no-tokens.txt").touch()  # exists but empty: hermetic default for --tokens-file

    block = tdir / "block"
    block.mkdir()
    (block / "requests.py").write_text("raise ImportError('blocked for test')\n")

    def run(*argv, env_extra=None, py=sys.executable):
        argv = list(argv)
        if "--tokens-file" not in argv:
            argv += ["--tokens-file", str(tdir / "no-tokens.txt")]  # hermetic: never read the skill's real tokens.txt
        env = {k: v for k, v in os.environ.items() if k not in ("MINERU_TOKEN", "MINERU_TOKENS")}
        env["HOME"] = str(home)
        if env_extra:
            env.update(env_extra)
        p = subprocess.run([py, str(SCRIPT), *argv], capture_output=True, text=True,
                           env=env, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def rt(name, argv, want_code, pattern, env_extra=None, py=sys.executable):
        code, out = run(*argv, env_extra=env_extra, py=py)
        check(name, code == want_code and re.search(pattern, out),
              f"code={code} want={want_code} out={out[:200]!r}")
        return out

    # usage / args
    rt("cli: no args -> 2", [], 2, r"usage:")
    rt("cli: --help -> 0", ["--help"], 0, r"--probe")
    rt("cli: --file+--dir exclusive", ["--file", str(tdir / "other.pdf"), "--dir", str(tdir / "in"),
                                       "--output", str(tdir / "o")], 2, r"not allowed with")
    rt("cli: missing --output -> 2", ["--file", str(tdir / "other.pdf")], 2, r"required")
    rt("cli: workers=0 -> 2", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                               "--workers", "0", "--token", tok], 2, r">= 1")

    # tokens
    out = rt("cli: no token -> 1", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"), "--dry-run"],
             1, r"No API token found")
    check("cli: no token, no traceback", "Traceback" not in out)

    # files
    rt("cli: missing file -> 1", ["--file", str(tdir / "missing.pdf"), "--output", str(tdir / "o"), "--token", tok],
       1, r"file not found")
    rt("cli: bad ext -> 1", ["--file", str(tdir / "in/notes.txt"), "--output", str(tdir / "o"), "--token", tok],
       1, r"unsupported type")
    out = rt("cli: dry-run ok -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                      "--token", tok, "--dry-run"], 0, r"Dry run OK")
    out = rt("cli: dir mixed -> 0", ["--dir", str(tdir / "in"), "--output", str(tdir / "o"),
                                     "--token", tok, "--dry-run"], 0, r"Dry run OK")
    check("cli: dotfiles silent", ".DS_Store" not in out)
    check("cli: bad ext visible in dir mode", "notes.txt" in out)
    (tdir / "txtOnly").mkdir()
    (tdir / "txtOnly" / "a.txt").write_text("x")
    rt("cli: all-rejected dir -> 1", ["--dir", str(tdir / "txtOnly"), "--output", str(tdir / "o"),
                                      "--token", tok, "--dry-run"], 1, r"No valid input files")
    rt("cli: bad --dir -> 2", ["--dir", str(tdir / "nope"), "--output", str(tdir / "o"),
                               "--token", tok, "--dry-run"], 2, r"not a directory")
    rt("cli: missing --tokens-file -> 2", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                           "--tokens-file", str(tdir / "absent-tokens.txt"), "--dry-run"],
       2, r"tokens-file not found")

    # state file
    (home / ".mineru").mkdir(exist_ok=True)
    key = __import__("hashlib").sha256(tok.encode()).hexdigest()[:12]
    (home / ".mineru" / "state.json").write_text(json.dumps({key: {"exhausted": date.today().isoformat()}}))
    rt("cli: exhausted today -> 1", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                     "--token", tok, "--dry-run"], 1, r"exhausted or invalid today")
    (home / ".mineru" / "state.json").write_text(
        json.dumps({key: {"exhausted": (date.today() - timedelta(days=1)).isoformat()}}))
    rt("cli: stale date resets -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                       "--token", tok, "--dry-run"], 0, r"Dry run OK")
    (home / ".mineru" / "state.json").write_text(json.dumps({key: {"dead": True}}))
    rt("cli: dead token -> 1", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                "--token", tok, "--dry-run"], 1, r"exhausted or invalid today")
    (home / ".mineru" / "state.json").unlink()

    # resume + tilde
    (tdir / "o2" / "other").mkdir(parents=True)
    rt("cli: resume skip -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o2"),
                                 "--token", tok, "--resume", "--dry-run"], 0, r"Skipping 1")
    (home / "vault" / "good").mkdir(parents=True)
    out = rt("cli: tilde expands", ["--dir", str(tdir / "in"), "--output", "~/vault", "--token", tok,
                                    "--resume", "--dry-run"], 0, r"Skipping 1")
    check("cli: no literal ~ dir", not Path.cwd().joinpath("~").exists() and "~" not in {d.name for d in tdir.iterdir()})

    # pages / probe / extra-formats validation
    for bad in ["1-", "abc", "5-2", "0-3", "1,,2"]:
        rt(f"cli: --pages '{bad}' -> 2", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                          "--pages", bad, "--token", tok], 2, r"pages")
    rt("cli: valid pages -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                 "--pages", "1-10,15,20-30", "--token", tok, "--dry-run"], 0, r"Dry run OK")
    out = rt("cli: pages+dir warning", ["--dir", str(tdir / "in"), "--output", str(tdir / "o"),
                                        "--pages", "1-5", "--token", tok, "--dry-run"], 0, r"applies to every file")
    rt("cli: --probe 0 -> 2", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                               "--probe", "0", "--token", tok], 2, r"1 and 200")
    rt("cli: --probe+--pages -> 2", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                     "--probe", "3", "--pages", "1-5", "--token", tok], 2, r"mutually exclusive")
    rt("cli: probe on office file -> 2", ["--file", str(tdir / "doc.docx"), "--output", str(tdir / "o"),
                                          "--probe", "--token", tok], 2, r"PDFs and images only")
    rt("cli: probe dry-run plans -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                         "--probe", "--token", tok, "--dry-run"], 0, r"Probe planned")
    rt("cli: bad --extra-formats -> 2", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                         "--extra-formats", "pdf,docx", "--token", tok], 2, r"unknown 'pdf'")
    rt("cli: good --extra-formats -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o"),
                                          "--extra-formats", "docx,html", "--token", tok, "--dry-run"],
       0, r"Dry run OK")

    # check-token CLI surface
    rt("cli: --check-token alone, no token -> 1", ["--check-token"], 1, r"No API token found")
    rt("cli: --check-token+--dry-run -> 2", ["--check-token", "--dry-run", "--token", tok], 2, r"drop --dry-run")
    out = rt("cli: --check-token without requests -> 1", ["--check-token", "--token", tok],
             1, r"requests is required for --check-token", env_extra={"PYTHONPATH": str(block)})

    # missing requests
    rt("cli: dry-run without requests -> 0", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o3"),
                                              "--token", tok, "--dry-run"], 0, r"Dry run OK",
       env_extra={"PYTHONPATH": str(block)})
    rt("cli: parse without requests -> 1", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o3"),
                                            "--token", tok], 1, r"requests is required",
       env_extra={"PYTHONPATH": str(block)})

    # old interpreter gate
    old_py = "/usr/bin/python3"
    if Path(old_py).exists():
        v = subprocess.run([old_py, "-c",
                            "import sys; sys.exit(0 if sys.version_info < (3, 10) else 1)"],
                           capture_output=True).returncode
        if v == 0:
            out = rt("cli: py<3.10 gated -> 1", ["--help"], 1, r"Python 3\.10\+ required", py=old_py)
            check("cli: py<3.10 no traceback", "Traceback" not in out)
        else:
            print("SKIP cli: py<3.10 gate (no old interpreter)")

    # unreachable network -> clean error
    rt("cli: unreachable net -> 1", ["--file", str(tdir / "other.pdf"), "--output", str(tdir / "o4"),
                                     "--token", tok], 1, r"Cannot reach mineru\.net",
       env_extra={"http_proxy": "http://127.0.0.1:1", "https_proxy": "http://127.0.0.1:1"})

    shutil.rmtree(tdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Doc-drift checks: SKILL.md CLI table vs --help, stamps, size
# ---------------------------------------------------------------------------
def drift_tests():
    section("doc drift")
    argv = sys.argv[1:]
    skill_md = Path(argv[argv.index("--skill-md") + 1]) if "--skill-md" in argv else DEFAULT_SKILL_MD

    help_proc = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                               capture_output=True, text=True, timeout=60)
    help_flat = " ".join((help_proc.stdout + help_proc.stderr).split())

    text = skill_md.read_text()
    table = re.findall(r"^(--[a-z-]+)(?:\s+\S+)?\s+(.*)$", text, re.MULTILINE)
    doc_flags = {}
    for flag, rest in table:
        doc_flags[flag.lstrip("-")] = rest

    # every documented flag exists in --help
    missing = [f for f in doc_flags if f"--{f}" not in help_flat]
    check("drift: documented flags exist in --help", not missing, f"missing: {missing}")

    # every script flag is documented (skip -h/--help)
    help_flags = set(re.findall(r"--([a-z][a-z-]+)", help_flat)) - {"help"}
    undocumented = sorted(help_flags - set(doc_flags))
    check("drift: script flags documented in SKILL.md", not undocumented, f"undocumented: {undocumented}")

    # defaults match (skip doc placeholders like <skill>/… — machine paths can't match them)
    mismatches = []
    for flag, rest in doc_flags.items():
        dm = re.search(r"\(default: ([^)]+)\)", rest)
        if not dm or "<" in dm.group(1):
            continue
        if f"(default: {dm.group(1)})" not in help_flat:
            mismatches.append(f"--{flag}: doc says {dm.group(1)!r}")
    check("drift: defaults match --help", not mismatches, str(mismatches))

    # verified stamps
    check("drift: SKILL.md has verified stamp", re.search(r"verified \w+ 20\d\d", text, re.IGNORECASE) is not None)
    check("drift: api_reference.md has verified stamp",
          re.search(r"verified", API_REF.read_text(), re.IGNORECASE) is not None)

    # progressive disclosure
    body_lines = len(text.splitlines())
    check("drift: SKILL.md body under 500 lines", body_lines < 500, f"{body_lines} lines")

    # requirements
    check("drift: requirements.txt pins requests",
          "requests" in (SKILL_DIR / "requirements.txt").read_text())


def main():
    unit_tests()
    cli_tests()
    drift_tests()
    total = PASSED[0] + FAILED[0]
    print(f"\n{'=' * 50}\n{PASSED[0]}/{total} passed, {FAILED[0]} failed")
    sys.exit(1 if FAILED[0] else 0)


if __name__ == "__main__":
    main()
