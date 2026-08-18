#!/usr/bin/env python3
"""
MinerU cloud API parser — PDF / Word / PPT / images → Markdown.

Design goals (make this the only thing you need to run MinerU):
- Multi-token pool: rotate on daily-limit (-60018), drop invalid tokens (A0202/A0211)
- Pre-flight checks: file existence, extension, 200 MB size cap, token presence
- Error-code-aware retries: never retry non-retryable API errors
- Resume: skip files whose output directory already exists
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


def api_call(token, method, url, **kw) -> dict:
    resp = requests.request(method, url, headers=headers(token), timeout=kw.pop("timeout", 60), **kw)
    result = resp.json()
    if result.get("code") != 0:
        raise APIError(result.get("code"), result.get("msg", "unknown API error"))
    return result


def process_file(pool: TokenPool, file_path: Path, output_dir: Path, index, total,
                 model, language, enable_formula, enable_table, page_ranges):
    """Parse one file. Returns (ok, stem, error_msg_or_none)."""
    stem = file_path.stem

    if (output_dir / stem).exists():
        print(f"  [{index+1}/{total}] ⏭️  {stem}")
        return True, stem, None

    print(f"  [{index+1}/{total}] 📤 {stem}", end="", flush=True)

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
                "model_version": model,
                "enable_formula": enable_formula,
                "enable_table": enable_table,
            }
            if language != "auto":
                payload["language"] = language
            if page_ranges:
                payload["page_ranges"] = page_ranges
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
                        zip_path = output_dir / f"{stem}.zip"
                        zip_path.write_bytes(requests.get(results[0]["full_zip_url"], timeout=300).content)
                        extract_dir = output_dir / stem
                        with zipfile.ZipFile(zip_path) as zf:
                            zf.extractall(extract_dir)
                        zip_path.unlink()
                        md = extract_dir / "full.md"
                        if md.exists():
                            md.rename(extract_dir / f"{stem}.md")
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


def main():
    parser = argparse.ArgumentParser(
        description="MinerU cloud API parser (PDF/Word/PPT/images → Markdown)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", help="Input directory (PDF/Word/PPT/images)")
    group.add_argument("--file", help="Single file path")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--token", help="API token (placed first in the pool; env/tokens.txt tokens are still used)")
    parser.add_argument("--tokens-file", help=f"Read tokens from file, one per line (default: {default_tokens_file()})")
    parser.add_argument("--workers", "-w", type=int, default=5, help="Concurrent workers (default: 5)")
    parser.add_argument("--resume", action="store_true", help="Skip files whose output directory already exists")
    parser.add_argument("--model", default="vlm", choices=["pipeline", "vlm", "MinerU-HTML"],
                        help="Model version (default: vlm)")
    parser.add_argument("--language", default="auto", choices=["auto", "en", "ch"],
                        help="Document language (default: auto)")
    parser.add_argument("--pages", help="Page ranges, e.g. '1-10,15,20-30' (bypasses the 200-page limit)")
    parser.add_argument("--no-formula", action="store_true", help="Disable formula recognition")
    parser.add_argument("--no-table", action="store_true", help="Disable table extraction")
    parser.add_argument("--dry-run", action="store_true", help="Validate files and tokens, then exit (no network, no dependencies)")
    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers must be >= 1")

    if args.pages:
        if not re.fullmatch(r"\s*\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*\s*", args.pages):
            parser.error('--pages must look like "1-10,15,20-30"')
        for part in args.pages.split(","):
            nums = [int(n) for n in part.split("-")]
            if nums[0] < 1 or (len(nums) == 2 and nums[0] > nums[1]):
                parser.error(f"invalid page range '{part.strip()}' (pages start at 1, start must not exceed end)")
        if args.dir:
            print("⚠️  --pages applies to every file in the directory")

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

    # --- tokens ---
    tokens = load_tokens(args)
    if not tokens:
        print(f"❌ No API token found. Set MINERU_TOKEN / MINERU_TOKENS, use --token, "
              f"or create {default_tokens_file()} (one token per line).\n   Get one at {TOKEN_URL}")
        sys.exit(1)
    pool = TokenPool(tokens)

    if args.resume:
        original = len(input_files)
        input_files = [f for f in input_files if not (output_dir / f.stem).exists()]
        if skipped := original - len(input_files):
            print(f"⏭️  Skipping {skipped} already-processed file(s)")

    print(f"\n📚 {len(input_files)} file(s) | workers: {args.workers} | model: {args.model} "
          f"| tokens: {len(tokens)} ({len(pool.available())} active)")
    print(f"🔑 Token pool:\n{pool.report()}\n")

    if args.dry_run:
        total_mb = sum(f.stat().st_size for f in input_files) / 1024 / 1024
        if rejected:
            print(f"🚫 {len(rejected)} file(s) would be rejected (listed above)")
        if not pool.available():
            print(f"⛔ All tokens exhausted or invalid today — parsing would fail. "
                  f"Add tokens or clear the state file tomorrow ({STATE_FILE}).")
            sys.exit(1)
        print(f"✅ Dry run OK — {len(input_files)} file(s), {total_mb:.1f} MB total, "
              f"{len(pool.available())} active token(s). Ready to parse.")
        return

    if requests is None:
        print("❌ requests is required to parse (--help and --dry-run work without it): "
              "pip install requests")
        sys.exit(1)

    if not input_files:
        print("✅ Nothing to do")
        return

    if not pool.available():
        print(f"⛔ All tokens exhausted or invalid today (state: {STATE_FILE}). "
              "Add more tokens or clear the state file tomorrow.")
        sys.exit(1)

    # --- connectivity check with a clear error instead of a stack trace ---
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

    success, failures = 0, []
    start = time.time()
    interrupted = False
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    process_file, pool, f, output_dir, i, len(input_files),
                    args.model, args.language,
                    not args.no_formula, not args.no_table, args.pages,
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
