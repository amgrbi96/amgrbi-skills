---
name: prospero-search
description: Search the PROSPERO registry for registered systematic reviews and check for duplicate or overlapping reviews before registering a new one. Use when the user mentions PROSPERO, systematic review registration, checking for duplicate reviews, or asks whether their research question has already been studied — even if they don't explicitly say 'PROSPERO'. Also triggers on mentions of 'protocol registration', 'review overlap', 'CRD number lookup', or 'prospective register'. Useful for researchers planning systematic reviews, scoping reviews, or meta-analyses who need to verify novelty before registration.
---

# PROSPERO Systematic Review Search & Duplicate Check

Search the PROSPERO international prospective register of systematic reviews and detect whether a planned review duplicates existing registered reviews.

## When to use this skill

- A researcher wants to check if their planned systematic review overlaps with existing reviews
- Someone asks to search PROSPERO by keywords, status, year, region, or funder
- A user needs to verify novelty of a research question for systematic review registration
- Someone asks to look up a CRD accession number (e.g., CRD420251023387)
- Protocol registration preparation for Cochrane, JBI, or other SR methodologies

## How PROSPERO's API works

The PROSPERO search API is undocumented and was reverse-engineered from their frontend JavaScript. Read `references/api_reference.md` for the full specification including request/response formats, filter options, and authentication.

Key points:
- **Base URL**: `https://www.crd.york.ac.uk/PROSPERO/api/` (the frontend Axios instance uses this as baseURL; all API paths are relative to it)
- **Search endpoint**: `POST https://www.crd.york.ac.uk/PROSPERO/api/search`
- **View endpoint**: `GET https://www.crd.york.ac.uk/PROSPERO/api/view/<CRD>`
- **Auth**: The `prospero-auth-token` header is mandatory — the API rejects requests without it. Generate it per-request by base64-encoding the current millisecond timestamp (`btoa(Date.now().toString())` in JS, `base64.b64encode(str(int(time.time() * 1000)))` in Python). The frontend also sends `prospero-access-token` (a login session token), but this is absent for anonymous users and not needed for search.
- **Required headers**: Only `Content-Type: application/json` and `prospero-auth-token` are required. `Accept` and `Referer` are not required (tested by removing each one against the live API). See `references/api_reference.md` for the full test matrix.

## Workflow

### Step 1: Extract search terms

From the user's research question or protocol, extract the core **Population** and **Intervention** terms. Use field codes for precision:

```
"diabetes:PA AND metformin:IV"    → 544 hits (targeted)
"diabetes AND metformin"          → 1275 hits (broader)
```

Available field codes: `TI` (title), `PA` (population), `IV` (intervention), `CS` (condition), `OP` (outcomes), `CM` (comparator), `KW` (keywords), `AN` (CRD number), `RQ` (review question), `MS` (MeSH terms). Boolean operators (`AND`, `OR`), exact phrases (`"..."`), wildcards (`diabet*`), parentheses, and proximity operators (`NEAR`, `NEAR3`, `ADJ`) all work.

**MeSH search**: Use `MeSH DESCRIPTOR <term>` for exact MeSH matching, or `MeSH DESCRIPTOR <term> EXPLODE` to include narrower MeSH terms. Example: `MeSH DESCRIPTOR Diabetes Mellitus EXPLODE` → 15,476 hits (vs 5,373 without EXPLODE).

**Field code grouping**: Use parentheses to group terms before a field code: `("multiple sclerosis" OR ms):TI`.

If the user provides specific CRD numbers, use the view endpoint directly (see Step 3).

### Step 2: Build and execute the search

Construct the API request. A minimal search looks like:

```json
{
  "term": "<search terms>",
  "page": 1,
  "nperpage": 20,
  "sort": "TI",
  "sortorder": "ASC",
  "filters": [],
  "download": false,
  "actual": "<same as term>"
}
```

**Filters** use a specific format (see `references/api_reference.md` for full details):

| Filter name | Values | Example |
|---|---|---|
| `reviewstatus` | `Ongoing`, `Completed`, `Discontinued` | `[{"name": "reviewstatus", "value": ["Ongoing"]}]` |
| `recordtype` | `Clinical`, `Animal`, `Cochrane` | `[{"name": "recordtype", "value": ["Clinical"]}]` |
| `yearfirstpublished` | Year strings | `[{"name": "yearfirstpublished", "value": ["2024", "2025"]}]` |
| `region` | `Europe`, `Asia`, `Africa`, `Americas`, `Oceania` | `[{"name": "region", "value": ["Europe"]}]` |
| `funders` | Funder names (lowercase, from aggs) | `[{"name": "funders", "value": ["other"]}]` |

For duplicate checking, filter to `Ongoing` reviews only — completed reviews are less concerning for registration purposes.

For the first pass, 20 results is usually enough. Only paginate further if initial results show borderline overlaps.

### Step 3: Analyze results

Extract only the useful fields from the response. Strip noise (`_index`, `_id`, `_score`, `sort`, `highlight`, `_ignored`) — it adds nothing to the analysis.

**From the search response**, extract per hit:
- `accessionnumber` — CRD number
- `title` — strip HTML tags (`<p>`, `<highlight>`)
- `reviewstatus` — Ongoing / Completed
- `recordtype` — Clinical, Cochrane, etc.
- `yearfirstpublished` — year
- `recordid` — internal ID

**From the aggregations** (`aggs`), extract overview stats:
- `reviewstatus` — count of Ongoing vs Completed
- `recordtype` — count by type
- `yearfirstpublished` — distribution by year

**For PICOS comparison**, use the view endpoint on specific records:
```
GET https://www.crd.york.ac.uk/PROSPERO/api/view/<accessionnumber>
```
The `json` field contains 14-15 blocks with `{caption, PublishedHTML}` pairs. Block structure varies by record template — search by caption across all blocks, don't hardcode block indices. Key captions:

| Caption | PICOS element |
|---|---|
| `Population` | **P** — patient group |
| `Intervention(s) or exposure(s)` | **I** — treatment/exposure |
| `Comparator(s) or control(s)` | **C** — comparison |
| `Main outcomes` | **O** — outcome measures |
| `Study design` | **S** — design type |
| `Condition or domain being studied` | Condition |
| `Medical Subject Headings` | MeSH terms |
| `Country` | Country |
| `Stage of the review at this submission` | Review stage |
| `Review team members` | Team |
| `Review type` | Review methodology |

The `record` field provides status metadata: `PublicationStatus`, `EditingStatus`, `TemplateVariantCaption` (review type), `IsLiving` (living systematic review flag).

Only call the view endpoint for records that look like potential duplicates from the search results. Don't call it for every result.

### Step 4: Duplicate / overlap assessment

Compare each PROSPERO result against the proposed review using PICOS elements (extracted from the view endpoint):

| Element | What to compare |
|---|---|
| **P**opulation | Same or overlapping patient group? |
| **I**ntervention | Same or overlapping treatment/exposure? |
| **C**omparator | Same or overlapping comparison? |
| **O**utcomes | Same or overlapping outcome measures? |
| **S**tudy design | Same review type (systematic, meta-analysis, scoping)? |

Score overlap as **matched elements / 5**. Flag reviews scoring **3 or higher** as potential duplicates.

### Step 5: Propose differentiations (when overlap detected)

When overlap >= 3/5, suggest specific PICOS refinements to differentiate the proposed review:

| Element | Narrowing strategy | Example |
|---|---|---|
| Population | Restrict age, setting, severity | Adults 18-65 -> community-dwelling adults 65+ |
| Intervention | Narrow dosage, delivery, duration | Exercise -> supervised resistance training 3x/week |
| Comparator | Add comparison the existing review lacks | Usual care -> usual care + attention control |
| Outcomes | Focus on different outcome types | Clinician-reported -> patient-reported outcomes |
| Study design | Restrict design type | Any design -> RCTs only |

Present the differentiated PICOS to the user for acceptance or further refinement.

### Step 6: Present results

Format the output clearly:

```
PROSPERO Search Results
=======================
Query: "<search terms>"
Filters applied: [list filters]
Total results: <count> (Ongoing: X, Completed: Y)

Potential Overlaps:
-------------------
1. [CRD#######] Title...
   Status: Ongoing | Type: Clinical | Year: 2025
   Country: China | Review type: Systematic review of interventions
   Population: [extracted population]
   Intervention: [extracted intervention]
   Comparator: [extracted comparator]
   Outcomes: [extracted outcomes]
   MeSH: [MeSH terms if available]
   PICOS Overlap: X/5
   Matched elements: [P, I, ...]
   Suggested differentiation: [specific changes]

Unique Review Candidates:
--------------------------
[CRD#######] Title... — no significant overlap

Conclusion:
-----------
[your assessment and recommendations]
```

## Error handling

| Error | Response |
|---|---|
| HTTP 429 (rate limited) | Wait 5 seconds, retry once. If still 429, report unavailability and suggest manual check at https://www.crd.york.ac.uk/prospero |
| HTTP 5xx | Retry once after 3 seconds. If still failing, report unavailability |
| Network timeout (>30s) | Report unavailability, suggest manual search |
| Invalid response | Log the issue, report what was received |

## Constraints

- **Rate limiting**: Send one request at a time. No parallel PROSPERO queries.
- **Max 3 refinement cycles**: After 3 rounds of differentiation attempts, ask the user explicitly before continuing.
- **PICOS extraction**: The search endpoint returns limited fields (title, status, record type, CRD number, year). For full PICOS data (population, intervention, comparator, outcomes, study design, country, MeSH terms, review stage), call the view endpoint (`/api/view/<CRD>`) on individual records. Only do this for records flagged as potential duplicates, not for every result.
- **MeSH search**: Use `MeSH DESCRIPTOR <term>` syntax in the search query. The MeSH tree browser endpoint (`/api/search/meshtree`) exists but returns empty responses — use the main search API instead.

## Bundled resources

- `references/api_reference.md` — Full PROSPERO API specification with request/response examples, filter format, pagination, and a complete Python code example. Read this before making API calls.
- `scripts/test_api.py` — Run `python3 scripts/test_api.py` to validate the API is reachable and see example responses.
