---
name: flashcards
description: "Create high-yield study flashcards from any source material (PDF book, lecture notes, markdown, plain text). Use when: (1) the user wants flashcards / Anki cards / a study deck from a document or topic, (2) turning a chapter/lecture/article into review cards, (3) capturing a single concept or fact as a flashcard to add to a deck, (4) exporting cards to Anki (.apkg) or Markdown. Emits Markdown for review then optionally Anki. Enforces one-fact-per-card atomicity and a high-yield filter so output is condensed, not exhaustive."
---

# flashcards

Turn source material into high-yield flashcards. **Condensation — not coverage — is the purpose.** Every card must earn its place; trivia is dropped, not carded. Output is Markdown (the reviewable source of truth) then optionally Anki (`.apkg`).

Three card types, chosen deliberately per fact: **concept** (frameworks/answers), **cloze** (a specific fact drilled), **reversed** (a pair drilled both directions).

## Setup

The builder needs `genanki`. Install once:

```bash
pip install --user --break-system-packages genanki   # macOS system Python
# or: pip install genanki                             # if you manage your own env
```

All packaging is done by `scripts/build_cards.py` — no card logic lives in the script; it only transforms a `cards.json` manifest into `.md` or `.apkg`.

## The manifest: `cards.json`

Before building, produce a `cards.json` — an array of card records. This is the editable source of truth; both Markdown and Anki are derived from it.

```json
[
  {
    "id": "akathisia-ladder",
    "deck": "Psychosis::EPS",
    "type": "concept",
    "front": "How is akathisia treated?",
    "back": "1. Reduce the current antipsychotic dose.\n2. Switch to monotherapy.\n3. Switch to quetiapine/olanzapine.\n4. Propranolol 30–80 mg/day.\n5. Mirtazapine or mianserin.",
    "tags": ["EPS", "akathisia"],
    "hint": { "type": "5-step algorithm", "landmarks": "" }
  },
  {
    "id": "lithium-toxic-threshold",
    "deck": "Mood::Lithium",
    "type": "cloze",
    "cloze": "Lithium becomes toxic above {{c1::1.5 mmol/L}}; above {{c2::3 mmol/L}} consider hemodialysis.",
    "tags": ["lithium", "toxicology"],
    "hint": { "type": "threshold card", "landmarks": "" }
  },
  {
    "id": "pde5-mechanism",
    "deck": "Sexual::ED",
    "type": "reversed",
    "front": "Sildenafil",
    "back": "PDE-5 inhibitor (enhances penile blood inflow)",
    "tags": ["ED"],
    "hint": { "type": "", "landmarks": "" }
  }
]
```

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Stable slug; anchors the Anki note id so re-imports **update** rather than duplicate |
| `deck` | yes | Hierarchical via `::` (`Topic::Subtopic`); subdecks auto-created |
| `type` | yes | `concept` \| `cloze` \| `reversed` |
| `front` / `back` | concept, reversed | The prompt and answer body |
| `cloze` | cloze only | Text with `{{c1::gap}}` markers |
| `extra` | cloze, optional | Shown on the back of a cloze card |
| `tags` | optional | Auto-namespaced under the deck name |
| `hint` | optional | `{ "type": …, "landmarks": … }` — see step 6 |

## Building

```bash
# Markdown first (for review)
python3 scripts/build_cards.py cards.json --format md --out deck.md --deck-name "Topic"

# Anki after review (one file, importable)
python3 scripts/build_cards.py cards.json --format apkg --out deck.apkg --deck-name "Topic"

# Both at once (writes deck.md + deck.apkg)
python3 scripts/build_cards.py cards.json --format md,apkg --out deck --deck-name "Topic"
```

Run from the skill directory. Input/output paths are relative to your working directory.

---

## How to author cards

Two **branches**: *batch* (a whole source → a deck) is the default; *capture* (one fact → append) is the lighter path. Steps 2–4 are shared.

### Batch branch — whole source to deck

#### 1. Digest the source
Read the material and pull out the *load-bearing* knowledge into rough notes. Do not paraphrase away detail that matters (doses, thresholds, sequence order). **Done when:** every distinct unit of knowledge is captured and trivia is set aside.

#### 2. Yield gate — keep only what's worth remembering
Drop anything that fails all three of these: (a) **load-bearing** — the rest of the material depends on it; (b) **testable fact** — a dose, definition, criterion, mechanism, or sign; (c) **decision rule** — something a practitioner must recall to act. Eponyms, history, and background go. **Done when:** nothing low-yield remains. *This is the condensation step — be ruthless.*

#### 3. Atomize — one fact per card
Split each kept unit so each card tests exactly one thing. Read [`references/card-quality.md`](references/card-quality.md) for the five rules (atomic, short front, minimal back, visual over prose, no trivia) and before/after examples. **Done when:** every card tests one unambiguous thing and its back carries only the answer.

#### 4. Type each card — concept / cloze / reversed
Pick the **minimal** type that tests the fact (see the table in `card-quality.md`):
- **concept** — frameworks, algorithms, multi-item answers
- **cloze** — a specific fact inside a sentence (dose, number, single word)
- **reversed** — a pair you must recall in both directions

Don't reach for cloze when concept works; don't reach for reversed when one direction suffices. **Done when:** every card has a justified type and the minimal fields for that type are filled.

#### 5. Write `cards.json`
Assemble the records into the manifest, matching the schema above. Use stable, descriptive `id` values. **Done when:** the file is valid JSON and every record has its required fields.

#### 6. Author hints
For each card, decide whether a hint helps. Read [`references/hint-rules.md`](references/hint-rules.md) for the rules (type = shape only; landmarks only when they add a framework; empty when type suffices; never leak). Most cards need only a `type` line; many need no hint at all. **Done when:** every card has a `type` line, and a `landmarks` only where a real framework aids recall.

#### 7. Build Markdown and **stop for review**
```bash
python3 scripts/build_cards.py cards.json --format md --out deck.md --deck-name "Topic"
```
Show the Markdown to the user. **Do not build Anki yet.** This checkpoint exists because a wrong fact shipped into a spaced-repetition deck is actively harmful — the user reviews first. **Done when:** the user approves the cards.

#### 8. Build Anki (after approval)
```bash
python3 scripts/build_cards.py cards.json --format apkg --out deck.apkg --deck-name "Topic"
```
**Done when:** the `.apkg` is written and the reported note count matches the card count.

### Capture branch — one fact to an existing deck

For adding a single card as you encounter something worth remembering (no source to digest):

1. **Yield gate** — is this worth remembering long-term? If no, stop.
2. **Atomize** — one fact; consult [`references/card-quality.md`](references/card-quality.md) if unsure.
3. **Type** — concept / cloze / reversed, minimal.
4. **Append** one record to the existing `cards.json` (stable `id` so it merges cleanly), then rebuild (`--format md` to review, `--format apkg` to ship).

This is steps 2–4 of batch, applied to one fact.

---

## Completion check

Before declaring done, every card must clear:
- **Yield gate** (load-bearing / testable / decision rule) — else drop it.
- **Atomic** — one fact each — else split it.
- **Minimal type** — concept before cloze before reversed.
- **No-leak hint** — type is shape only; landmarks empty unless a framework helps.
- **Reviewed Markdown** before any Anki build.
