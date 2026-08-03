# Hint rules

Read this at the **author hints** step. A hint is a scaffold that helps you *recall* the answer without *revealing* it. The cardinal failure mode is **leak** — a hint that restates the answer.

## Two-layer hint structure

Each card may carry a hint with two fields:

| Field | Where it shows | What it does |
|---|---|---|
| `type` | Always visible, under the prompt | Names the answer's **shape** (count, algorithm, threshold, sections) |
| `landmarks` | Click-to-reveal (Anki `{{hint:}}`) | A **framework** to cue recall: named phases, thresholds, decision branches, mnemonics |

## Rule 1 — Type line = answer shape only

The `type` describes *what kind of answer* is expected, never *what the answer is about*. The prompt already states the topic; restating it wastes the line.

**Leak (bad):** `type: "Drug-induced parkinsonism — 3 steps"` (restates the topic)
**Good:** `type: "3-step algorithm"`

Valid shape words: `N-step algorithm`, `N-point list`, `threshold card`, `N-section framework`, `time-phased protocol`, `by-X matrix`, `decision tree`, `mnemonic — <name>`.

## Rule 2 — Landmarks only when they add a framework

A landmark is useful **only** when it gives a structure the answer's content doesn't already hand you. Use it for:
- **Named phases** of a time/step sequence (e.g. `≤48h / 48–72h / 72h–1wk / >1wk`)
- **Thresholds** that structure a decision (e.g. `Green / Amber / Red` levels)
- **Decision branches** (e.g. `On anti-manic? NO → … / YES → …`)
- **Mnemonics** (e.g. `5 causes, all start with A`)

Do **not** use landmarks when:
- the type alone tells you enough ("3-step algorithm" — you recall the 3 steps)
- the items *are* the answer (listing them *is* leaking)
- the card is a simple list or single rule

## Rule 3 — Empty landmarks > leaking landmarks

When in doubt, **leave `landmarks` empty**. A missing landmark costs nothing; a leaking landmark ruins the card. The single highest-value editing move is deleting a landmark that restates the answer.

**Leak (bad):**
```
type: 3-step algorithm
landmarks: Reduce dose
           Switch
           Anticholinergic
```
(That *is* the answer.) → **Fix:** `type: "3-step algorithm"`, `landmarks: ""`.

**Good:**
```
type: time-phased protocol (4 phases)
landmarks: ≤48h
           48–72h
           72h–1wk
           >1wk
```
(The phases are the framework; the *content* of each phase is what you must recall.)

## The leak test

Before writing a landmark, ask: **"If I only saw this landmark, could I shortcut to the answer?"** If yes, it leaks — delete or shorten it. A landmark should tell you *what buckets to fill*, never *what's in them*.

## Default: no hint

Most cards need nothing beyond their `type` line, and many need no hint at all. Default to empty; add a landmark only when a card is genuinely hard to recall cold and a named framework would help. Hint density should be low across a deck — if most cards carry landmarks, you are over-hinting.
