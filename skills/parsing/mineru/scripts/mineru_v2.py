#!/usr/bin/env python3
"""
MinerU cloud API parser — PDF / Word / PPT / images → Markdown.

Design goals (make this the only thing you need to run MinerU):
- Multi-token pool: rotate on daily-limit (-60018), drop invalid tokens (A0202/A0211)
- Pre-flight checks: file existence, extension, 200 MB size cap, token presence
- Waste guards: skip existing outputs, warn on text-layer PDFs, page-budget estimates
- Error-code-aware retries: never retry non-retryable API errors
- Resume: skip files whose output directory already exists
- --probe: sample-parse with both models to pick one empirically
- --check-token: read-only pool health check, zero page spend
- --dry-run: validate everything without touching the network (works without `requests`)

Requires Python 3.10+ (`str | None` unions, walrus operators) — enforced below.
"""

import argparse
import hashlib
import itertools
import json
import os
import re
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

if sys.version_info < (3, 10):
    print(f"❌ Python 3.10+ required, found {sys.version.split()[0]}. "
          "Re-run with a newer interpreter (e.g. python3.10+).")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None  # checked in main; lets --help/--dry-run work without deps

API_BASE = "https://mineru.net/api/v4"
TOKEN_URL = "https://mineru.net/user-center/api-token"

SUPPORTED_EXTS = {".pdf", ".docx", ".pptx", ".jpg", ".jpeg", ".png"}
MAX_FILE_BYTES = 200 * 1024 * 1024  # API hard limit: 200 MB
EXTRA_FORMATS = {"docx", "html", "latex"}
DAILY_PAGES_PER_TOKEN = 1000

# API error codes that should never be retried for the same file/token combo.
FATAL_FILE_CODES = {"-500", "-60005", "-60006", "-60023"}  # bad param / too large / too many pages / region
FATAL_TOKEN_CODES = {"A0202", "A0211"}  # invalid / expired token
QUOTA_CODES = {"-60018"}  # daily page limit reached for this token

STATE_DIR = Path.home() / ".mineru"
STATE_FILE = STATE_DIR / "state.json"


class APIError(Exception):
    """MinerU API returned a non-zero code."""

    def __init__(self, code, msg):
        self.code = str(code)
        self.msg = msg
        super().__init__(f"[{self.code}] {msg}")


def default_tokens_file() -> Path:
    return Path(__file__).resolve().parent.parent / "tokens.txt"


PAGES_RE = re.compile(r"\s*\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*\s*")


def validate_page_ranges(parser, value: str, flag: str):
    if not PAGES_RE.fullmatch(value):
        parser.error(f'{flag} must look like "1-10,15,20-30"')
    for part in value.split(","):
        nums = [int(n) for n in part.split("-")]
        if nums[0] < 1 or (len(nums) == 2 and nums[0] > nums[1]):
            parser.error(f"invalid page range '{part.strip()}' in {flag} "
                         "(pages start at 1, start must not exceed end)")


def count_pages(value: str) -> int:
    """Page count of a validated ranges expression, e.g. '1-10,15' -> 11."""
    total = 0
    for part in value.split(","):
        nums = [int(n) for n in part.split("-")]
        total += nums[-1] - nums[0] + 1
    return total


def load_tokens(args) -> list[str]:
    """Token sources, in priority order: --token, MINERU_TOKENS, MINERU_TOKEN, tokens.txt."""
    tokens = []
    if args.token:
        tokens.append(args.token.strip())
    for env in ("MINERU_TOKENS", "MINERU_TOKEN"):
        for t in os.environ.get(env, "").split(","):
            t = t.strip()
            if t and t not in tokens:
                tokens.append(t)
    tf = Path(args.tokens_file).expanduser() if args.tokens_file else default_tokens_file()
    if args.tokens_file and not tf.is_file():
        print(f"❌ --tokens-file not found: {tf}")
        sys.exit(2)
    if tf.exists():
        try:
            text = tf.read_text()
        except OSError as e:
            print(f"❌ Cannot read tokens file {tf}: {e}")
            sys.exit(2)
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line not in tokens:
                tokens.append(line)
    return tokens


def mask(token: str) -> str:
    return f"{token[:4]}…{token[-4:]}" if len(token) > 8 else "****"


class TokenPool:
    """Round-robin token assignment with daily-exhaustion and dead-token tracking.

    Exhaustion (daily limit) resets with the date; dead tokens (invalid/expired)
    stay dead until removed from the source and the state entry is cleared.
    """

    def __init__(self, tokens: list[str]):
        self._all = list(tokens)
        self._cycle = itertools.cycle(self._all)
        self._lock = threading.Lock()
        self.exhausted: dict[str, str] = {}  # token -> date it hit the daily cap
        self.dead: set[str] = set()
        self._load_state()

    def _key(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()[:12]

    def _load_state(self):
        try:
            state = json.loads(STATE_FILE.read_text())
            today = date.today().isoformat()
            for t in self._all:
                entry = state.get(self._key(t), {})
                if entry.get("dead"):
                    self.dead.add(t)
                elif entry.get("exhausted") == today:
                    self.exhausted[t] = today
        except (OSError, ValueError):
            pass  # first run or corrupt state — start fresh

    def save_state(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        state = {}
        for t in self._all:
            entry = {}
            if t in self.dead:
                entry["dead"] = True
            elif t in self.exhausted and self.exhausted[t] == today:
                entry["exhausted"] = today
            if entry:
                state[self._key(t)] = entry
        STATE_FILE.write_text(json.dumps(state, indent=2))

    def available(self) -> list[str]:
        return [t for t in self._all if t not in self.dead and t not in self.exhausted]

    def next(self) -> str | None:
        with self._lock:
            if not self.available():
                return None
            for _ in range(len(self._all)):
                t = next(self._cycle)
                if t not in self.dead and t not in self.exhausted:
                    return t
            return None

    def mark_exhausted(self, token: str):
        with self._lock:
            self.exhausted[token] = date.today().isoformat()
        print(f"\n⚠️  Token {mask(token)} hit daily page limit — rotating")

    def mark_dead(self, token: str, why: str):
        with self._lock:
            self.dead.add(token)
        print(f"\n❌ Token {mask(token)} removed from pool: {why}")

    def revive(self, token: str):
        with self._lock:
            self.dead.discard(token)
            self.exhausted.pop(token, None)

    def report(self) -> str:
        lines = []
        for t in self._all:
            status = "dead" if t in self.dead else (
                "daily limit hit" if t in self.exhausted else "active"
            )
            lines.append(f"  {mask(t)}  {status}")
        return "\n".join(lines)


def headers(token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def check_file(f: Path) -> str | None:
    """Return an error string if the file can't be sent, else None."""
    if not f.exists():
        return "file not found"
    if f.is_dir():
        return "directory (not a file)"
    if not f.is_file():
        return "not a regular file"
    if f.suffix.lower() not in SUPPORTED_EXTS:
        return f"unsupported type '{f.suffix}' (supported: {', '.join(sorted(SUPPORTED_EXTS))})"
    size = f.stat().st_size
    if size == 0:
        return "empty file"
    if size > MAX_FILE_BYTES:
        return f"{size / 1024 / 1024:.0f} MB exceeds the 200 MB API limit"
    return None


def pdf_precheck_warnings(files: list[Path], pool: TokenPool) -> list[str]:
    """Zero-dependency, best-effort waste guards over raw PDF bytes.

    Estimates pages from the largest /Count in the page tree (hidden in some
    compressed PDFs) and flags PDFs that already carry a text layer, where a
    local parser usually suffices. All warnings are advisory — nothing is blocked.
    """
    warnings = []
    total_pages, counted = 0, 0
    for f in files:
        if f.suffix.lower() != ".pdf":
            continue
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if b"/Font" in data:
            warnings.append(
                f"⚠️  {f.name}: text layer detected — a local parser (pdf-to-markdown / pymupdf-pdf) "
                "is likely enough; MinerU pays off for formulas, complex layout, or dense tables")
        counts = [int(n) for n in re.findall(rb"/Count\s+(\d+)", data)]
        est = max(counts) if counts else None
        if est:
            total_pages += est
            counted += 1
            if est > 200:
                warnings.append(
                    f"⚠️  {f.name}: ~{est} pages (estimated) exceeds the 200-page API limit — "
                    "split with --pages 1-200, 201-400, …")
    capacity = DAILY_PAGES_PER_TOKEN * len(pool.available())
    if capacity and total_pages > capacity:
        warnings.append(
            f"⚠️  estimated ~{total_pages} pages across {counted} PDF(s) vs ~{capacity} pages/day "
            f"pool capacity ({len(pool.available())} active token(s)) — the run will likely stop at "
            "the daily limit; add tokens or split across days with --pages + --resume")
    return warnings


def api_call(token, method, url, **kw) -> dict:
    resp = requests.request(method, url, headers=headers(token), timeout=kw.pop("timeout", 60), **kw)
    result = resp.json()
    if result.get("code") != 0:
        raise APIError(result.get("code"), result.get("msg", "unknown API error"))
    return result


def out_stem_for(stem: str, opts) -> str:
    """Output subdirectory name. --pages chunks get a range suffix (book-201-400)
    so sequential range runs land in separate folders instead of silently
    skipping each other via the existing-output check."""
    if opts.pages and not getattr(opts, "is_probe", False):
        return f"{stem}-{re.sub(r'[^0-9-]+', '_', opts.pages)}"
    return stem


def process_file(pool: TokenPool, file_path: Path, output_dir: Path, index, total, opts):
    """Parse one file. Returns (ok, stem, error_msg_or_none).

    `opts` is the argparse namespace (model, language, no_formula, no_table,
    pages, extra_formats_list) — or a per-run copy with overrides (see --probe).
    """
    stem = file_path.stem
    out_stem = out_stem_for(stem, opts)

    if (output_dir / out_stem).exists():
        print(f"  [{index+1}/{total}] ⏭️  {out_stem}")
        return True, stem, None

    print(f"  [{index+1}/{total}] 📤 {out_stem}", end="", flush=True)

    last_err = None
    attempts = 0
    while True:
        token = pool.next()
        if token is None:
            msg = ("no available tokens — all hit the daily limit or are invalid. "
                   "Add tokens via MINERU_TOKENS or tokens.txt "
                   f"(state resets daily; stale state: rm {STATE_FILE})")
            print(f" ⛔ {msg}")
            return False, stem, msg

        try:
            # 1. request pre-signed upload URL
            payload = {
                "files": [{"name": file_path.name, "data_id": stem}],
                "model_version": opts.model,
                "enable_formula": not opts.no_formula,
                "enable_table": not opts.no_table,
            }
            if opts.language != "auto":
                payload["language"] = opts.language
            if opts.pages:
                payload["page_ranges"] = opts.pages
            if opts.extra_formats_list:
                payload["extra_formats"] = list(opts.extra_formats_list)
            result = api_call(token, "POST", f"{API_BASE}/file-urls/batch", json=payload)
            batch_id = result["data"]["batch_id"]
            upload_url = result["data"]["file_urls"][0]

            # 2. upload raw bytes (no auth header — signature is in the URL)
            print(" ⏳", end="", flush=True)
            upload_resp = requests.put(upload_url, data=file_path.read_bytes(), timeout=300)
            if upload_resp.status_code not in (200, 203):
                raise Exception(f"upload failed: HTTP {upload_resp.status_code}")

            # 3. poll for completion
            print(" 🔄", end="", flush=True)
            for _ in range(120):  # 10 min cap
                results = api_call(
                    token, "GET",
                    f"{API_BASE}/extract-results/batch/{batch_id}",
                    timeout=30,
                )["data"]["extract_result"]
                if results:
                    state = results[0].get("state")
                    if state == "done":
                        # 4. download + extract zip
                        print(" 📥", end="", flush=True)
                        extract_dir = output_dir / out_stem
                        extract_dir.mkdir(parents=True, exist_ok=True)  # probe writes into nested dirs
                        zip_path = output_dir / f"{out_stem}.zip"
                        zip_path.write_bytes(requests.get(results[0]["full_zip_url"], timeout=300).content)
                        with zipfile.ZipFile(zip_path) as zf:
                            zf.extractall(extract_dir)
                        zip_path.unlink()
                        md = extract_dir / "full.md"
                        if md.exists():
                            md.rename(extract_dir / f"{out_stem}.md")
                        print(" ✅")
                        return True, stem, None
                    if state == "failed":
                        raise APIError("-60010", results[0].get("err_msg", "parse failed"))
                time.sleep(5)
            raise APIError("-60008", "timed out waiting for result")

        except APIError as e:
            last_err = str(e)
            if e.code in FATAL_TOKEN_CODES:
                pool.mark_dead(token, e.msg)
                continue  # rotate to another token without consuming a retry
            if e.code in QUOTA_CODES:
                pool.mark_exhausted(token)
                continue  # rotate to another token without consuming a retry
            if e.code in FATAL_FILE_CODES:
                hint = {
                    "-60006": " — retry with --pages 1-200, 201-400, …",
                    "-60005": " — file exceeds the 200 MB API limit",
                }.get(e.code, "")
                print(f" ❌ {last_err}{hint}")
                return False, stem, f"{last_err}{hint}"  # retrying won't help this file
            # other API errors: retry with backoff
        except Exception as e:  # network errors, HTTP hiccups
            last_err = str(e)

        attempts += 1
        if attempts >= 5:
            break
        print(f" 🔄r{attempts}", end="", flush=True)
        time.sleep(2 ** (attempts - 1))

    print(f" ❌ {last_err}")
    return False, stem, last_err


def run_probe(pool: TokenPool, files: list[Path], output_dir: Path, args,
              models: list[str], pages_expr: str | None) -> bool:
    """Sample-parse each file with each model into output/<stem>-probe/<model>/.

    Returns True when every probe succeeded. Sample dirs are stable across
    models, so probing different models in separate runs coexists.
    """
    total = len(files) * len(models)
    all_ok, i = True, 0
    for f in files:
        pages = pages_expr if f.suffix.lower() == ".pdf" else None
        for model in models:
            probe_opts = argparse.Namespace(**{**vars(args), "model": model, "pages": pages, "is_probe": True})
            ok, _, _ = process_file(pool, f, output_dir / f"{f.stem}-probe" / model, i, total, probe_opts)
            all_ok = all_ok and ok
            i += 1
        for model in models:
            print(f"    {model}: {output_dir / f.stem}-probe/{model}/{f.stem}/{f.stem}.md")
    pool.save_state()
    return all_ok


def ensure_online(output_dir: Path):
    """requests present, mineru.net reachable, output writable — exit(1) with a clear error if not."""
    if requests is None:
        print("❌ requests is required to parse (--help and --dry-run work without it): "
              "pip install requests")
        sys.exit(1)
    try:
        requests.get("https://mineru.net", timeout=10)
    except requests.RequestException as e:
        print(f"❌ Cannot reach mineru.net: {e}")
        sys.exit(1)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"❌ Cannot create output directory {output_dir}: {e}")
        sys.exit(1)


def run_check_token(args) -> int:
    """Verify every pool token against the API without spending pages.

    GET on a nonexistent task id discriminates auth health: -60012 (task not
    found) means the token authenticated fine; A0202/A0211 mark it dead.
    Best-effort — derived from documented codes, verdicts may be inconclusive.
    """
    if requests is None:
        print("❌ requests is required for --check-token: pip install requests")
        return 1
    tokens = load_tokens(args)
    if not tokens:
        print(f"❌ No API token found. Set MINERU_TOKEN / MINERU_TOKENS, use --token, "
              f"or create {default_tokens_file()} (one token per line).\n   Get one at {TOKEN_URL}")
        return 1
    pool = TokenPool(tokens)
    print(f"\n🔌 Checking {len(tokens)} token(s) against the API (read-only, no page spend)…")
    for t in tokens:
        label = mask(t)
        valid = False
        try:
            api_call(t, "GET", f"{API_BASE}/extract/task/selftest-probe", timeout=30)
            valid = True  # no error at all — authenticated fine
        except APIError as e:
            if e.code in FATAL_TOKEN_CODES:
                pool.mark_dead(t, e.msg)
                print(f"  {label}  ❌ invalid ({e.msg}) — remove it from your token sources")
            elif e.code == "-60012":
                valid = True  # task-not-found proves auth passed
            else:
                print(f"  {label}  ❓ inconclusive ({e}) — treated as usable")
        except requests.RequestException as e:
            print(f"❌ Cannot reach mineru.net: {e}")
            return 1
        if valid:
            print(f"  {label}  ✅ valid")
            if t in pool.dead or t in pool.exhausted:
                pool.revive(t)
                print(f"  {label}  ♻️  revived (was marked dead/exhausted in state)")
    pool.save_state()
    active = len(pool.available())
    print(f"\n{active}/{len(tokens)} token(s) active (state: {STATE_FILE})")
    return 0 if active else 1


def main():
    parser = argparse.ArgumentParser(
        description="MinerU cloud API parser (PDF/Word/PPT/images → Markdown)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dir", help="Input directory (PDF/Word/PPT/images)")
    group.add_argument("--file", help="Single file path")
    parser.add_argument("--output", help="Output directory (required unless --check-token)")
    parser.add_argument("--token", help="API token (placed first in the pool; env/tokens.txt tokens are still used)")
    parser.add_argument("--tokens-file", help=f"Read tokens from file, one per line (default: {default_tokens_file()})")
    parser.add_argument("--workers", "-w", type=int, default=5, help="Concurrent workers (default: 5)")
    parser.add_argument("--resume", action="store_true", help="Skip files whose output directory already exists")
    parser.add_argument("--model", default=None, choices=["pipeline", "vlm", "MinerU-HTML"],
                        help="Model version (default: vlm; with --probe: probe only this model)")
    parser.add_argument("--language", default="auto", choices=["auto", "en", "ch"],
                        help="Document language (default: auto)")
    parser.add_argument("--pages", help="Page ranges, e.g. '1-10,15,20-30' (bypasses the 200-page limit)")
    parser.add_argument("--extra-formats", help="Extra deliverables: comma list from docx,html,latex (default: none)")
    parser.add_argument("--probe", nargs="?", const=3, type=int, metavar="N",
                        help="Sample-parse to pick a model, then stop: first N pages (default: 3) "
                             "or --probe-pages; runs pipeline+vlm, or only --model X")
    parser.add_argument("--probe-pages", help="Probe specific pages instead of the first N, e.g. '85-87,203' (PDFs only)")
    parser.add_argument("--check-token", action="store_true",
                        help="Verify every pool token against the API (read-only, no page spend), then exit")
    parser.add_argument("--no-formula", action="store_true", help="Disable formula recognition")
    parser.add_argument("--no-table", action="store_true", help="Disable table extraction")
    parser.add_argument("--dry-run", action="store_true", help="Validate files and tokens, then exit (no network, no dependencies)")
    args = parser.parse_args()

    # --- flag validation ---
    if args.workers < 1:
        parser.error("--workers must be >= 1")

    if args.pages:
        validate_page_ranges(parser, args.pages, "--pages")
        if args.dir:
            print("⚠️  --pages applies to every file in the directory")

    probe_active = args.probe is not None or bool(args.probe_pages)
    if args.probe is not None:
        if args.pages:
            parser.error("--probe and --pages are mutually exclusive")
        if not 1 <= args.probe <= 200:
            parser.error("--probe must be between 1 and 200 pages")
    if args.probe_pages:
        if args.pages:
            parser.error("--probe-pages and --pages are mutually exclusive")
        validate_page_ranges(parser, args.probe_pages, "--probe-pages")

    # probe configuration: explicit --model probes just it; otherwise pipeline+vlm
    probe_models = [args.model] if (probe_active and args.model) else \
                   (["pipeline", "vlm"] if probe_active else None)
    probe_pages_expr = (args.probe_pages or f"1-{args.probe}") if probe_active else None
    args.model = args.model or "vlm"  # full-parse default

    args.extra_formats_list = []
    if args.extra_formats:
        for x in args.extra_formats.split(","):
            x = x.strip()
            if x and x not in args.extra_formats_list:
                args.extra_formats_list.append(x)
        bad = [x for x in args.extra_formats_list if x not in EXTRA_FORMATS]
        if bad:
            parser.error(f"--extra-formats: unknown '{','.join(bad)}' (valid: docx,html,latex)")

    if args.check_token and args.dry_run:
        parser.error("--check-token is itself a live check; drop --dry-run")
    if not args.check_token:
        if not (args.dir or args.file):
            parser.error("one of the arguments --dir --file is required")
        if not args.output:
            parser.error("the following argument is required: --output")

    if args.check_token:
        sys.exit(run_check_token(args))

    output_dir = Path(args.output).expanduser()

    # --- collect and validate files ---
    if args.dir:
        input_dir = Path(args.dir).expanduser()
        if not input_dir.is_dir():
            parser.error(f"--dir not found or not a directory: {input_dir}")
        raw_files = [f for f in sorted(input_dir.iterdir()) if not f.name.startswith(".")]
    else:
        raw_files = [Path(args.file).expanduser()]
    input_files, rejected = [], []
    for f in raw_files:
        err = check_file(f)
        if err:
            rejected.append((f.name, err))
        else:
            input_files.append(f)
    for name, err in rejected:
        print(f"🚫 {name}: {err}")
    if rejected and not input_files:
        print("❌ No valid input files")
        sys.exit(1)

    if probe_active:
        unsupported = [f.name for f in input_files
                       if f.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png")]
        if unsupported:
            parser.error(f"--probe supports PDFs and images only (page ranges don't apply to: {', '.join(unsupported)})")
        img_ranges = [f.name for f in input_files
                      if f.suffix.lower() in (".jpg", ".jpeg", ".png") and args.probe_pages]
        if img_ranges:
            parser.error(f"--probe-pages applies to PDFs only (images are single-page): {', '.join(img_ranges)}")

    # --- tokens ---
    tokens = load_tokens(args)
    if not tokens:
        print(f"❌ No API token found. Set MINERU_TOKEN / MINERU_TOKENS, use --token, "
              f"or create {default_tokens_file()} (one token per line).\n   Get one at {TOKEN_URL}")
        sys.exit(1)
    pool = TokenPool(tokens)

    if args.resume:
        original = len(input_files)
        input_files = [f for f in input_files if not (output_dir / out_stem_for(f.stem, args)).exists()]
        if skipped := original - len(input_files):
            print(f"⏭️  Skipping {skipped} already-processed file(s)")

    print(f"\n📚 {len(input_files)} file(s) | workers: {args.workers} | model: {args.model} "
          f"| tokens: {len(tokens)} ({len(pool.available())} active)")
    print(f"🔑 Token pool:\n{pool.report()}\n")

    precheck = pdf_precheck_warnings(input_files, pool)
    for w in precheck:
        print(w)
    if precheck:
        print()

    if args.dry_run:
        total_mb = sum(f.stat().st_size for f in input_files) / 1024 / 1024
        if rejected:
            print(f"🚫 {len(rejected)} file(s) would be rejected (listed above)")
        if not pool.available():
            print(f"⛔ All tokens exhausted or invalid today — parsing would fail. "
                  f"Add tokens or clear the state file tomorrow ({STATE_FILE}).")
            sys.exit(1)
        note = ""
        if probe_models is not None:
            cost = count_pages(probe_pages_expr) * len(probe_models)
            note = (f"\n🔬 Probe planned: pages {probe_pages_expr} × {' + '.join(probe_models)} "
                    f"(~{cost} pages/file of quota)")
        print(f"✅ Dry run OK — {len(input_files)} file(s), {total_mb:.1f} MB total, "
              f"{len(pool.available())} active token(s). Ready to parse.{note}")
        return

    if not input_files:
        print("✅ Nothing to do")
        return

    if not pool.available():
        print(f"⛔ All tokens exhausted or invalid today (state: {STATE_FILE}). "
              "Add more tokens or clear the state file tomorrow.")
        sys.exit(1)

    ensure_online(output_dir)

    if probe_models is not None:
        cost = count_pages(probe_pages_expr) * len(probe_models)
        print(f"\n🔬 Probing pages {probe_pages_expr} with {' + '.join(probe_models)} "
              f"(~{cost} pages/file of quota)")
        all_ok = run_probe(pool, input_files, output_dir, args, probe_models, probe_pages_expr)
        if all_ok:
            print("\n🔬 Compare the sample(s) per file, then run the full parse with "
                  "--model <winner> (plus --extra-formats / --no-formula / --no-table as needed)")
        sys.exit(0 if all_ok else 1)

    success, failures = 0, []
    start = time.time()
    interrupted = False
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    process_file, pool, f, output_dir, i, len(input_files), args,
                ): f
                for i, f in enumerate(input_files)
            }
            for future in as_completed(futures):
                ok, name, _err = future.result()
                if ok:
                    success += 1
                else:
                    failures.append(name)
    except KeyboardInterrupt:
        interrupted = True

    pool.save_state()
    if interrupted:
        print("\n🛑 Interrupted — token state saved; re-run with --resume to continue")
        sys.exit(130)

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"✅ Success: {success}  ❌ Failed: {len(failures)}  ⏱️  {elapsed/60:.1f} min")
    print(f"🔑 Token pool after run:\n{pool.report()}")
    print(f"\n📊 Summary (JSON):\n{json.dumps({'success': success, 'failed': failures, 'output': str(output_dir)}, ensure_ascii=False)}")
    print(f"\n📁 Output: {output_dir}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
