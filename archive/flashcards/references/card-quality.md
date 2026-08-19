# Card quality rules

Read this at the **atomize** step. Every card must pass every rule below before it is written to `cards.json`. A card that fails any rule is either fixed or dropped — never shipped as-is.

The single test: **could a student who knows this card act on it?** If the answer is no, the card tests trivia, not knowledge.

## The five rules

### 1. Atomic — one fact per card
A card tests exactly one thing. If the back has two independent facts, split it into two cards. Splitting feels like more work up front; it is the whole point — spaced repetition drills each fact on its own schedule.

**Bad** (two facts in one card):
```
Front: NMS
Back:  Develops within 4 weeks of starting an antipsychotic. Treat by stopping
       the drug, giving dantrolene/bromocriptine, and supportive care.
```
**Good** (split):
```
Card A — Front: NMS onset window        Back: Within 4 weeks of starting/increasing an antipsychotic
Card B — Front: NMS pharmacological Rx  Back: Stop drug; dantrolene ± bromocriptine (supportive care primary)
```

The exception is a *single coherent unit* like an ordered algorithm (the steps are one mental object) — keep those together as a concept card.

### 2. Short, specific front — one unambiguous answer
The front should cue a single answer with no reasonable alternative. If you read the front and think "well, it depends," the front is broken. Few words beats many.

**Bad:** `Tell me about lithium` (could go anywhere)
**Good:** `Lithium dialysis threshold` → `>3 mmol/L`

### 3. Minimal back — no unnecessary text
The back carries the answer and nothing else. No restating the question, no throat-clearing ("The answer is…"), no filler. Every word on the back is either the answer or essential context to disambiguate it.

**Bad back:** `The most important thing to remember about akathisia is that you should first reduce the dose of the current antipsychotic medication.`
**Good back:** `1. Reduce the current antipsychotic dose.`

### 4. Visual over prose — lists, tables, structure
Prose is the enemy of recall. Convert it to structure: numbered lists for sequences, bullets for sets, tables for comparisons, bold for sub-headers. The eye and the memory prefer structure.

**Bad back:** `Akathisia is treated by reducing the dose, then switching to monotherapy, then switching to quetiapine or olanzapine, then propranolol...`
**Good back:**
```
1. Reduce the dose.
2. Switch to monotherapy.
3. Switch to quetiapine/olanzapine.
4. Propranolol 30–80 mg/day.
5. Mirtazapine / mianserin.
```

### 5. No trivia — only things worth remembering long-term
This is the yield gate restated. Do not card:
- eponyms and researcher names (unless the name *is* the tested item, e.g. a syndrome name)
- historical background ("first described in 1899")
- context that explains but isn't tested
- anything you'd be fine forgetting

**Test:** if you forgot this fact forever, would it matter? If no, don't card it.

## Choosing the card type

Pick the **minimal** type that tests the fact. Don't reach for cloze when concept works; don't reach for reversed when one direction suffices.

| Type | Use when | Example |
|---|---|---|
| **Concept** | Frameworks, algorithms, multi-item answers, definitions needing explanation | "How is akathisia treated?" → 5-step ladder |
| **Cloze** | A specific fact *inside* a sentence: a dose, a number, a single word, a threshold | "Lithium toxic above {{c1::1.5 mmol/L}}" |
| **Reversed** | A pair you must recall in **both** directions | drug ↔ mechanism, term ↔ definition, sign ↔ disease |

Cloze is for drilling a precise gap; concept is for recalling a structure; reversed is for making a pair bidirectional. If a fact is just "know X", use concept. Only add reversed if you'd realistically be asked the pair backwards.

## Worked example: turning a paragraph into cards

Source paragraph:
> Lithium toxicity occurs above 1.5 mmol/L. The most important risk factors involve sodium handling: low-salt diet, dehydration, NSAIDs, ACE inhibitors, and diuretics. Above 3 mmol/L, hemodialysis is often required. Diuresis, if used, must be osmotic or forced alkaline — never thiazide or loop.

Yield gate: all load-bearing facts. No trivia to drop here.

Atomized (one fact each):
1. **Concept** — *Lithium toxicity risk factors* → `Sodium handling: low-salt diet, dehydration, NSAIDs, ACE inhibitors, diuretics. (Addison's.)`
2. **Cloze** — `Lithium becomes toxic above {{c1::1.5 mmol/L}}; above {{c2::3 mmol/L}} consider hemodialysis.`
3. **Cloze** — `For lithium toxicity diuresis, use osmotic or forced alkaline — {{c1::never}} thiazide or loop.`

That's 3 cards from one paragraph — each atomic, each testable, nothing wasted.
