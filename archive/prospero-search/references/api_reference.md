# PROSPERO API Reference

Complete specification for the PROSPERO search API, reverse-engineered from the frontend JavaScript (`main.3a4214f2.js`).

## Endpoint

```
POST https://www.crd.york.ac.uk/PROSPERO/api/search
```

## Authentication

No API key or login required. The frontend (`main.3a4214f2.js`) uses an Axios interceptor that generates a per-request token from the current timestamp:

```javascript
// From the frontend source (minified):
Or.interceptors.request.use(function(e) {
    e.headers["prospero-access-token"] = sessionStorage.getItem("token");  // null for anonymous users
    let t = (new Date).getTime();
    e.headers["prospero-auth-token"] = btoa(t.toString());
    return e;
});
```

Two headers are sent by the frontend:
1. **`prospero-auth-token`** (mandatory) — `btoa(Date.now().toString())`, i.e. base64-encoded millisecond timestamp. Generate a fresh value per request.
2. **`prospero-access-token`** (optional) — A session token stored after login. `null` for anonymous visitors. Not needed for search.

The `prospero-auth-token` header is mandatory. Omitting it returns HTTP 200 with:
```json
{"status": "error", "errormessage": "Error code: header value undefined"}
```

### Token generation

```python
# Python
import base64, time
token = base64.b64encode(str(int(time.time() * 1000)).encode()).decode()
```

```javascript
// JavaScript
const token = btoa(Date.now().toString());
```

## Required Headers

Tested by stripping headers one at a time against the live API. Only two are required:

```
Content-Type: application/json
prospero-auth-token: <generated token>
```

**What we tested (empirical results):**

| Header removed | Result |
|---|---|
| `prospero-auth-token` | `"Error code: header value undefined"` |
| `Content-Type` | `"Nothing to search for"` (body not parsed) |
| `Accept` | Works — not required |
| `Referer` | Works — not required |
| `Origin` | Works — not required |

**What the browser actually sends** (captured from Chrome DevTools "Copy as cURL"):

```
accept: application/json, text/plain, */*
accept-language: en-GB,en;q=0.9,ar-SA;q=0.8,ar;q=0.7,en-US;q=0.6
content-type: application/json
origin: https://www.crd.york.ac.uk
prospero-auth-token: <base64-encoded millisecond timestamp>
referer: https://www.crd.york.ac.uk/PROSPERO/search/simple
sec-ch-ua: "Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: same-origin
user-agent: <standard Chrome UA>
```

Notes:
- CDP `Network.requestWillBeSent` does not capture all headers — it missed `origin`, `accept-language`, `priority`, and `sec-fetch-*` compared to Chrome DevTools.
- The Axios code also sets `Cache-Control: no-cache`, `Pragma: no-cache`, `Expires: 0`, and `prospero-access-token` (session token). None of these appear in the DevTools capture either — Axios may set them but Chrome strips them before the network layer.
- The frontend uses a 10-second timeout (`Un={timeout:10000}`) on search calls.

## Request Body

```json
{
  "term": "search query terms",
  "page": 1,
  "nperpage": 20,
  "sort": "TI",
  "sortorder": "ASC",
  "filters": [],
  "download": false,
  "actual": "same as term"
}
```

| Field | Type | Description |
|---|---|---|
| `term` | string | Search query (see Search Syntax below) |
| `actual` | string | Mirror of `term`. Used for highlighting/tracking. |
| `page` | integer | Page number (1-indexed) |
| `nperpage` | integer | Results per page (tested up to 500, no enforced cap) |
| `sort` | string | Sort field: `TI` (title), `DA` (date), etc. |
| `sortorder` | string | `ASC` or `DESC` |
| `filters` | array | Server-side filters (see below) |
| `download` | boolean | `true` returns RIS citation per record. Not useful for PICOS — use `/api/view` instead. |

### Search syntax

Tested against the live API. All of these work:

| Syntax | Example | Result |
|---|---|---|
| Simple term | `diabetes` | 42,919 hits |
| AND | `type 2 diabetes AND metformin` | 1,275 hits |
| OR | `metformin OR insulin` | 13,257 hits |
| Exact phrase | `"systematic review" AND diabetes` | 36,684 hits |
| Wildcard | `diabet*` | 45,973 hits |
| Parentheses | `(diabetes OR hypertension) AND exercise` | 7,551 hits |
| Field code | `diabetes:TI` | 11,152 hits |
| Proximity (NEAR) | `hepatocellular NEAR liver` | Terms within 6 words |
| Proximity (NEARn) | `hepatocellular NEAR3 liver` | Terms within 3 words |
| Proximity (ADJ) | `hepatocellular ADJ liver` | Synonym for NEAR |
| MeSH term | `MeSH DESCRIPTOR Diabetes Mellitus` | 5,373 hits |
| MeSH explode | `MeSH DESCRIPTOR Diabetes Mellitus EXPLODE` | 15,476 hits |
| Field grouping | `("multiple sclerosis" OR ms):TI` | Group terms before field code |

**Phrase search**: Multiple words are automatically searched as a phrase unless a Boolean operator is present. Use quotes for clarity.

**Proximity operators**: `NEAR` (default 6 words apart), `NEAR3` (3 words apart), `ADJ` (synonym for NEAR). Word order matters — `A NEAR B` may return different results than `B NEAR A`.

**MeSH search**: Use `MeSH DESCRIPTOR <term>` for exact MeSH term matching, or append `EXPLODE` to include narrower terms in the MeSH hierarchy. MeSH terms can also be combined with other search syntax.

**Field code grouping**: Parentheses group terms before a field code. `("multiple sclerosis" OR ms):TI` restricts both terms to the Title field. Without parentheses, the field code applies only to the immediately preceding term.

### Field codes

Search specific fields using `<term>:<code>` syntax:

| Code | Field | Example |
|---|---|---|
| `TI` | Title | `diabetes:TI` |
| `PA` | Population | `diabetes:PA` |
| `IV` | Intervention | `metformin:IV` |
| `CS` | Condition studied | `diabetes:CS` |
| `OP` | Main outcomes | `mortality:OP` |
| `CM` | Comparator | `placebo:CM` |
| `KW` | Keywords | `exercise:KW` |
| `AN` | CRD accession number | `CRD42025:AN` |
| `RQ` | Review question | `efficacy:RQ` |
| `MS` | MeSH terms | `Diabetes Mellitus:MS` |

Combine field codes: `diabetes:PA AND metformin:IV` → 544 hits (vs 1,275 without field codes).
Group terms with parentheses: `("multiple sclerosis" OR ms):TI` restricts both to Title.

### Sort options

| Code | Sort by |
|---|---|
| `TI` | Title |
| `DA` | Date |

### Filter format

Filters use a specific array-of-objects format where each object has `name` (string) and `value` (array of strings):

```json
{
  "filters": [
    {"name": "reviewstatus", "value": ["Ongoing"]},
    {"name": "recordtype", "value": ["Clinical"]}
  ]
}
```

**Common mistake**: The key is `name` (not `field`), and `value` must be an array (not a string). Using the wrong format silently returns unfiltered results.

### Available filters

The API converts filter objects into query term modifications using hidden field codes. For example, `{"name": "reviewstatus", "value": ["Ongoing"]}` transforms the term `diabetes` into `(diabetes) AND "ongoing":rs`.

| Filter name | Field code | Valid values | Example |
|---|---|---|---|
| `reviewstatus` | `rs` | `Ongoing`, `Completed`, `Discontinued` | `[{"name": "reviewstatus", "value": ["Ongoing"]}]` |
| `recordtype` | `rt` | `Clinical`, `Animal`, `Cochrane` | `[{"name": "recordtype", "value": ["Clinical"]}]` |
| `yearfirstpublished` | `yr` | Year strings | `[{"name": "yearfirstpublished", "value": ["2024", "2025"]}]` |
| `region` | `re` | `Europe`, `Asia`, `Africa`, `Americas`, `Oceania` | `[{"name": "region", "value": ["Europe"]}]` |
| `funders` | `fi` | Funder names (lowercase, from aggregation data) | `[{"name": "funders", "value": ["other"]}]` |

The hidden field codes (`rs`, `rt`, `yr`, `re`, `fi`) can also be used directly in the search term, e.g. `"ongoing":rs AND diabetes`. Valid values for each filter come from the aggregation response (`aggs`).

**`dateinprospero` does not work** — the API ignores it and returns unfiltered results (tested against live API, term stays unchanged). Do not use it.

### Multi-filter example

```json
{
  "filters": [
    {"name": "reviewstatus", "value": ["Ongoing"]},
    {"name": "recordtype", "value": ["Clinical"]},
    {"name": "yearfirstpublished", "value": ["2024", "2025"]}
  ]
}
```

## Response Structure

The API returns an array with exactly one element containing an Elasticsearch-style response. Most of the response is noise — here's what to extract and what to skip:

**Useful fields:**

| Path | Description |
|---|---|
| `[0].hits` | Total hit count |
| `[0].retvals.hits.hits[]._source.accessionnumber` | CRD accession number (e.g., `CRD42024564418`) |
| `[0].retvals.hits.hits[]._source.title` | Review title (HTML-wrapped — strip `<p>`, `<highlight>` tags) |
| `[0].retvals.hits.hits[]._source.reviewstatus` | `Ongoing` or `Completed` |
| `[0].retvals.hits.hits[]._source.recordtype` | Record type (e.g., `Clinical`, `Cochrane`) |
| `[0].retvals.hits.hits[]._source.yearfirstpublished` | Publication year |
| `[0].retvals.hits.hits[]._source.recordid` | Internal record ID |
| `[0].retvals.aggs` | Aggregations (record type counts, year distribution, status, region, funders) — useful for overview |

**Aggregation fields** (`[0].retvals.aggs`):

| Aggregation | Contents |
|---|---|
| `recordtype` | Record type counts (Clinical, Animal, Cochrane) |
| `reviewstatus` | Status counts (Ongoing, Completed, Discontinued) |
| `yearfirstpublished` | Year distribution |
| `dateinprospero` | Date ranges (Last month, Last 6 months, etc.) — informational only, not usable as a filter |
| `region` | Geographic region counts (Europe, Asia, Africa, Americas, Oceania) |
| `funders` | Funding body counts (values are lowercase) |

**Noise to skip:**

| Path | Why skip |
|---|---|
| `[0].linenumber`, `[0].term`, `[0].note`, `[0].wrapper` | Metadata about the response itself |
| `hits[].sort` | Duplicates the title, used for sorting |
| `hits[].highlight` | HTML-highlighted version of title, redundant |
| `hits[]._index`, `hits[]._id`, `hits[]._score` | Elasticsearch internals |
| `hits[]._ignored` | Elasticsearch metadata |
| `retvals.hits.total` | Duplicates `[0].hits` |

### Response shape (condensed)

```json
[{
  "hits": 3583,
  "retvals": {
    "hits": {
      "hits": [{
        "_source": {
          "title": "<HTML-wrapped>",
          "reviewstatus": "Ongoing",
          "recordtype": "Clinical",
          "accessionnumber": "CRD420251023387",
          "yearfirstpublished": 2025,
          "recordid": 1023387
        }
      }]
    },
    "aggs": {}
  }
}]
```

### Pagination

`nperpage` has no enforced cap (tested up to 500). Pagination is 1-indexed. The last page returns fewer results; pages beyond the last return an empty `hits` array.

Calculate total pages: `ceil([0].hits / nperpage)`.

For duplicate checking, you typically don't need all pages — the first 20-50 results sorted by relevance are sufficient. Only paginate further if the initial results show borderline overlaps.

### Download mode (`download: true`)

Adds a `ris` field (RIS citation format) to each `_source`. Not useful for PICOS extraction — use the view endpoint instead for full review content.

### Individual record lookup (for full PICOS data)

The view endpoint returns structured review content including Population, Intervention, Comparator, Outcomes, and Study design:

```
GET https://www.crd.york.ac.uk/PROSPERO/api/view/<accessionnumber>
```

Returns `{"record": {...}, "json": [...]}` for valid records, or `{"record": {}, "json": []}` for non-existent ones.

**`record`** contains status metadata:

| Field | Description |
|---|---|
| `EditingStatus` | `In process`, etc. |
| `PublicationStatus` | `Registered`, etc. |
| `RecordStatusID` | Numeric status code |
| `RecordStatusMessage` | Status message text |
| `TemplateName` | Template used (e.g., `People v1`) |
| `TemplateVariantCaption` | Review type (e.g., `Systematic review of interventions`) |
| `IsLiving` | Whether it's a living systematic review |
| `Latest` | `Latest` if this is the current version |
| `previousversions` | Number of previous versions |

**`json`** is an array of 14-15 blocks. Each block has `blockcontent` → array of `{caption, PublishedHTML}` pairs. Strip HTML tags to get plain text. Note: `PublishedHTML` can be a string or a list — handle both.

**Important**: Block indices vary between record templates (e.g., `People v1` vs newer templates). Always search by caption across all blocks rather than hardcoding block indices.

| Block (approx.) | Key captions to search for |
|---|---|
| 0 | Title, authors, citation |
| 1 | Review title, Review type, Condition or domain being studied, Review objectives, Keywords, Country |
| 2 | Population, Intervention(s) or exposure(s), Comparator(s) or control(s), Study design, Context |
| 3 | Living systematic review methods |
| 4 | Date of first submission, Review timeline, Date of registration |
| 5 | Availability of full protocol |
| 6 | Searches, Search language restrictions, Link to search strategy |
| 7 | Data extraction, Risk of bias/quality assessment |
| 8 | **Main outcomes, Additional outcomes** |
| 9 | Strategy for data synthesis |
| 10 | **Stage of the review**, Publication of review results |
| 11 | Review team members, Review affiliation, Funding source |
| 12 | **Medical Subject Headings**, Review conflict of interest, Additional information |

Use the view endpoint only when you need full PICOS comparison data for a specific record. The search endpoint is sufficient for initial screening.

## Error responses

| Status | Meaning |
|---|---|
| 429 | Rate limited. Retry after a delay. |
| 5xx | Server error. Retry once. |
| Timeout | Network issue. The PROSPERO servers can be slow. |

The API does not appear to return structured error bodies — responses are typically empty or generic HTML on error.

## Complete request example

```python
import base64, json, re, time, urllib.request

def search_prospero(query, filters=None, page=1, per_page=20):
    token = base64.b64encode(str(int(time.time() * 1000)).encode()).decode()
    body = json.dumps({
        "term": query, "page": page, "nperpage": per_page,
        "sort": "TI", "sortorder": "ASC",
        "filters": filters or [], "download": False, "actual": query,
    }).encode()
    req = urllib.request.Request(
        "https://www.crd.york.ac.uk/PROSPERO/api/search",
        data=body, method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("prospero-auth-token", token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())[0]

def clean_title(html):
    return re.sub(r"<[^>]+>", "", html).strip()

def view_record(crd_number):
    token = base64.b64encode(str(int(time.time() * 1000)).encode()).decode()
    url = f"https://www.crd.york.ac.uk/PROSPERO/api/view/{crd_number}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("prospero-auth-token", token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def extract_field(block, caption):
    for item in block.get("blockcontent", []):
        if item.get("caption") == caption:
            html = item.get("PublishedHTML", "")
            if isinstance(html, dict):
                html = html.get("PublishedHTML", str(html))
            if isinstance(html, list):
                parts = []
                for x in html:
                    if isinstance(x, dict):
                        parts.append(x.get("PublishedHTML", ""))
                    else:
                        parts.append(str(x))
                html = " ".join(parts)
            return clean_title(html)
    return ""

def find_field(blocks, caption):
    """Search all blocks for a caption — blocks vary by record template."""
    for block in blocks:
        result = extract_field(block, caption)
        if result:
            return result
    return ""

def get_picos(crd_number):
    data = view_record(crd_number)
    blocks = data["json"]
    return {
        "population": find_field(blocks, "Population"),
        "intervention": find_field(blocks, "Intervention(s) or exposure(s)"),
        "comparator": find_field(blocks, "Comparator(s) or control(s)"),
        "outcomes": find_field(blocks, "Main outcomes"),
        "study_design": find_field(blocks, "Study design"),
        "condition": find_field(blocks, "Condition or domain being studied"),
        "country": find_field(blocks, "Country"),
        "mesh": find_field(blocks, "Medical Subject Headings"),
        "review_stage": find_field(blocks, "Stage of the review at this submission"),
        "team": find_field(blocks, "Review team members"),
        "status": data["record"].get("PublicationStatus", ""),
        "type": data["record"].get("TemplateVariantCaption", ""),
    }

# Example: search and get PICOS for top result
results = search_prospero(
    "diabetes:PA AND metformin:IV",
    filters=[{"name": "reviewstatus", "value": ["Ongoing"]}],
)
print(f"Total hits: {results['hits']}")
for hit in results["retvals"]["hits"]["hits"]:
    src = hit["_source"]
    print(f"  {src['accessionnumber']}  {src['reviewstatus']:10s}  "
          f"{src['recordtype']:10s}  {src['yearfirstpublished']}  "
          f"{clean_title(src['title'])[:70]}")

# Get full PICOS for the first result
crd = results["retvals"]["hits"]["hits"][0]["_source"]["accessionnumber"]
picos = get_picos(crd)
print(f"\nPICOS for {crd}:")
for k, v in picos.items():
    if v:
        print(f"  {k}: {v[:120]}")
```
