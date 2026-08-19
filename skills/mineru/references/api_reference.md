# MinerU API Reference

Verified against live docs at `https://mineru.net/apiManage/docs` and live API calls (Aug 2026).

MinerU exposes **two** APIs. Pick by use case:

| | Precision API (`/api/v4`) | Agent Lightweight API (`/api/v1`) |
|---|---|---|
| **Auth** | Bearer token (required) | None — IP rate-limited |
| **Output** | Markdown + JSON + DOCX/HTML/LaTeX + images | Markdown only |
| **Best for** | Batch, tables, formulas, multi-format | Quick single-file agent workflows |
| **Limits** | 200 MB / 200 pages per file · 1000 pages/day priority · 50 files/batch | 50 pages per file · single file |

Default to the **Precision API** — the scripts in this skill use it. Use the Agent API only when you have no token or need a throwaway Markdown-only parse.

---

## Precision API (`/api/v4`)

### Base URL

```
https://mineru.net/api/v4
```

### Auth

All requests need a Bearer token:

```
Authorization: Bearer YOUR_API_TOKEN
```

Create tokens at https://mineru.net/user-center/api-token

### Limits

- **File size**: ≤ 200 MB
- **Pages per file**: ≤ 200
- **Batch size**: ≤ 50 files per request
- **Daily quota**: 1000 pages at highest priority (extra pages still process at lower priority — not hard-blocked)

### Endpoints

#### Single File Parsing (URL)

**POST** `/extract/task`

```json
{
  "url": "https://example.com/doc.pdf",
  "model_version": "vlm",
  "is_ocr": false,
  "enable_formula": true,
  "enable_table": true,
  "language": "ch",
  "page_ranges": "1-10",
  "extra_formats": ["docx", "html"],
  "data_id": "my-document",
  "no_cache": false,
  "cache_tolerance": 900
}
```

Response:
```json
{
  "code": 0,
  "data": {"task_id": "xxx-xxx-xxx"},
  "msg": "ok",
  "trace_id": "xxx"
}
```

#### Get Task Result

**GET** `/extract/task/{task_id}`

```json
{
  "code": 0,
  "data": {
    "task_id": "xxx",
    "state": "done",
    "full_zip_url": "https://...",
    "err_msg": ""
  },
  "msg": "ok"
}
```

States: `pending` · `running` · `done` · `failed` · `converting`

#### Batch URL Parsing

**POST** `/extract/task/batch`

```json
{
  "files": [
    {"url": "https://example.com/doc1.pdf", "data_id": "doc1"},
    {"url": "https://example.com/doc2.pdf", "data_id": "doc2"}
  ],
  "model_version": "vlm"
}
```

Response: `{"code":0, "data":{"batch_id":"xxx"}, "msg":"ok"}`

#### Batch File Upload (local files)

**POST** `/file-urls/batch`

Returns pre-signed OSS upload URLs. Then `PUT` each file to its URL (no auth header on the PUT — the signature is in the URL).

```json
{
  "files": [{"name": "doc1.pdf", "data_id": "doc1"}],
  "model_version": "vlm"
}
```

Response:
```json
{
  "code": 0,
  "data": {
    "batch_id": "xxx",
    "file_urls": ["https://mineru.oss-...?Signature=..."]
  }
}
```

#### Get Batch Results

**GET** `/extract-results/batch/{batch_id}`

```json
{
  "code": 0,
  "data": {
    "batch_id": "xxx",
    "extract_result": [
      {"file_name": "doc.pdf", "state": "done", "full_zip_url": "https://..."}
    ]
  }
}
```

### Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `model_version` | string | `pipeline` | `pipeline` (fast), `vlm` (highest accuracy), `MinerU-HTML` (web-style) |
| `is_ocr` | bool | `false` | Force OCR on text PDFs |
| `enable_formula` | bool | `true` | LaTeX formula recognition |
| `enable_table` | bool | `true` | Table structure recognition |
| `language` | string | `ch` | `auto` \| `en` \| `ch` |
| `page_ranges` | string | all | `"1-10,15,20-30"` |
| `extra_formats` | array | `[]` | `["docx","html","latex"]` |
| `data_id` | string | — | Custom identifier |
| `no_cache` | bool | `false` | Bypass cache |
| `cache_tolerance` | int | 900 | Cache TTL (seconds) |

### Zero-cost token probe

`GET /extract/task/<any-nonexistent-id>` with a Bearer token discriminates auth health without creating tasks or spending pages: `-60012` (task not found) means the token authenticated fine; `A0202`/`A0211` mean invalid/expired. This is what the script's `--check-token` uses. Derived from the documented codes above — treat as best-effort until live-verified on your next token check.

---

## Agent Lightweight API (`/api/v1`)

Tokenless, Markdown-only, IP-rate-limited. For quick single-file parses without a token.

### Base URL

```
https://mineru.net/api/v1
```

### Limits

- No token required
- **≤ 50 pages per file**
- Single file (no batch)
- IP rate-limited (HTTP 429 on excess)
- Foreign URLs (github.com, aws.amazonaws.com, etc.) may be **regionally restricted** (`-60023`)

### Endpoints

#### Parse by URL

**POST** `/agent/parse/url`

```json
{
  "url": "https://example.com/doc.pdf",
  "file_name": "doc.pdf",
  "language": "ch",
  "enable_table": true,
  "is_ocr": false,
  "enable_formula": true,
  "page_range": "1-10"
}
```

Response: `{"code":0, "data":{"task_id":"xxx"}, "msg":"ok"}`

#### Parse by File Upload (signed PUT)

**POST** `/agent/parse/file`

Request:
```json
{"file_name": "doc.pdf", "language": "ch"}
```

Response:
```json
{
  "code": 0,
  "data": {"task_id": "xxx", "file_url": "https://oss-upload-url..."}
}
```

Then `PUT` the raw file bytes to `data.file_url` (signature is in the URL — no auth header).

#### Get Result

**GET** `/agent/parse/{task_id}`

```json
{
  "code": 0,
  "data": {
    "state": "done",
    "markdown_url": "https://cdn.../doc.md",
    "err_msg": ""
  }
}
```

States: `waiting-file` · `uploading` · `pending` · `running` · `done` · `failed`

When `state == "done"`, fetch Markdown from `data.markdown_url`.

---

## Error Codes

Verified codes from live docs + live calls:

| Code | Meaning |
|---|---|
| `0` | Success |
| `A0202` | Invalid token |
| `A0211` | Token expired |
| `-500` | Parameter error |
| `-30001`–`-30004` | Agent API errors (no token / rate limit / file issues) |
| `-60005` | File too large (>200 MB) |
| `-60006` | Too many pages (>200) |
| `-60008` | File read timeout |
| `-60010` | Parse failed |
| `-60012` | Task not found or expired |
| `-60018` | Daily limit reached |
| `-60023` | URL regionally restricted (foreign domains blocked) |
