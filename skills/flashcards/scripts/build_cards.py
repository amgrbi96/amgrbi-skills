#!/usr/bin/env python3
"""Build flashcards from a cards.json manifest into Markdown and/or Anki (.apkg).

Generalized from the Kanaan card builder. No hardcoded paths, no domain content —
everything is a CLI argument or a field on the card record.

USAGE
  build_cards.py cards.json --format md   --out deck.md
  build_cards.py cards.json --format apkg --out deck.apkg [--deck-name "Topic"]
  build_cards.py cards.json --format md,apkg --out deck     # writes deck.md + deck.apkg

cards.json schema (array of records):
  {
    "id":      "stable-slug",                  # required; anchors the Anki note id
    "deck":    "Topic::Subtopic",              # required; '::' nests subdecks
    "type":    "concept|cloze|reversed",        # required
    "front":   "question / prompt",            # concept & reversed
    "back":    "answer body",                  # concept & reversed
    "cloze":   "text with {{c1::gap}}",        # cloze only
    "tags":    ["tag1", "tag2"],               # optional
    "hint":    {"type": "shape line", "landmarks": "scaffold or empty"}  # optional
  }
"""
import argparse, json, re, html, hashlib, sys, os

# --------------------------------------------------------------------------- #
# Text parsing — reused from the Kanaan builder. Converts free-text card bodies
# (bullets, numbered lists, soft-wrapped paragraphs) into clean HTML or Markdown.
# --------------------------------------------------------------------------- #

_BULLET = re.compile(r'^[•\u2022\-\*]\s+')      # bullet markers
_NUMBER = re.compile(r'^\d+\.\s+')               # numbered list markers
_DOSE = re.compile(r'\d+(\.\d+)?\s*(mg|µg|mcg|ml|mmol|mmol/L|%)', re.I)


def is_bullet(s): return bool(_BULLET.match(s))
def is_numbered(s): return bool(_NUMBER.match(s))
def is_marker(s): return is_bullet(s) or is_numbered(s)
def strip_bullet(s): return _BULLET.sub('', s, count=1)
def strip_number(s): return _NUMBER.sub('', s, count=1)


def _is_subheader(s: str, prev: str, next_raw: str) -> bool:
    """Heuristic: is plain line `s` a sub-header introducing a list?

    Sub-headers are short noun phrases (<=6 words, no sentence punctuation) that
    sit immediately before a bullet/number marker. Guarded against the common
    false positive (a wrapped continuation of the previous bullet) by requiring
    the previous line to end with sentence punctuation.
    """
    if not next_raw or not is_marker(next_raw):
        return False
    if len(s.split()) > 6:
        return False
    if re.search(r'[.:;]\s*$', s):
        return False
    if prev:
        return prev[-1] in '.:!?'
    return True


def rejoin_wrapped_lines(body: str) -> list:
    """Rejoin soft-wrapped lines into logical lines.

    A plain line merges into the previous one unless it is a sub-header
    introducing the next list.
    """
    raw = [ln.rstrip() for ln in body.split('\n')]
    n = len(raw)

    def next_nonblank(idx):
        j = idx + 1
        while j < n and not raw[j].strip():
            j += 1
        return j

    rejoined = []
    for i, ln in enumerate(raw):
        s = ln.strip()
        if not s:
            if rejoined and rejoined[-1] != '':
                rejoined.append('')
            continue
        if is_marker(s):
            rejoined.append(s)
            continue
        j = next_nonblank(i)
        next_s = raw[j].strip() if j < n else ''
        prev_s = rejoined[-1] if rejoined and rejoined[-1] != '' else ''
        if _is_subheader(s, prev_s, next_s):
            rejoined.append(s)
        elif not prev_s:
            rejoined.append(s)
        else:
            rejoined[-1] = rejoined[-1] + ' ' + s
    while rejoined and rejoined[-1] == '':
        rejoined.pop()
    return rejoined


def body_to_html(body: str) -> str:
    """Convert a card body to styled HTML (<ul>/<ol>/<p>)."""
    lines = rejoin_wrapped_lines(body)
    out, para_buf, i, n = [], [], 0, len(lines)

    def flush(buf):
        if buf:
            out.append('<p>' + ' '.join(buf) + '</p>')
            buf.clear()

    while i < n:
        s = lines[i].strip()
        if not s:
            flush(para_buf); i += 1; continue
        if is_bullet(s):
            flush(para_buf); out.append('<ul>')
            while i < n and is_bullet(lines[i].strip()):
                out.append('  <li>' + html.escape(strip_bullet(lines[i].strip())) + '</li>')
                i += 1
            out.append('</ul>'); continue
        if is_numbered(s):
            flush(para_buf); out.append('<ol>')
            while i < n and is_numbered(lines[i].strip()):
                out.append('  <li>' + html.escape(strip_number(lines[i].strip())) + '</li>')
                i += 1
            out.append('</ol>'); continue
        # plain line — sub-header (bold) or paragraph
        j = i + 1
        while j < n and not lines[j].strip():
            j += 1
        if j < n and is_marker(lines[j].strip()):
            flush(para_buf)
            out.append('<p class="sub"><b>' + html.escape(s) + '</b></p>')
        else:
            para_buf.append(html.escape(s))
        i += 1
    flush(para_buf)
    return '\n'.join(out) if out else ''


def body_to_markdown(body: str) -> str:
    """Convert a card body to native Markdown (lists, bold sub-headers)."""
    lines = rejoin_wrapped_lines(body)
    out, para_buf, i, n = [], [], 0, len(lines)

    def flush(buf):
        if buf:
            out.append(' '.join(buf))
            buf.clear()

    while i < n:
        s = lines[i].strip()
        if not s:
            flush(para_buf); i += 1; continue
        if is_bullet(s):
            flush(para_buf)
            while i < n and is_bullet(lines[i].strip()):
                out.append('- ' + strip_bullet(lines[i].strip()))
                i += 1
            out.append(''); continue
        if is_numbered(s):
            flush(para_buf)
            num = 1
            while i < n and is_numbered(lines[i].strip()):
                out.append(f'{num}. ' + strip_number(lines[i].strip()))
                num += 1
                i += 1
            out.append(''); continue
        j = i + 1
        while j < n and not lines[j].strip():
            j += 1
        if j < n and is_marker(lines[j].strip()):
            flush(para_buf)
            out.append('**' + s + '**')
        else:
            para_buf.append(s)
        i += 1
    flush(para_buf)
    return '\n'.join(out).strip()


# --------------------------------------------------------------------------- #
# Stable ids — deterministic hashing so re-importing updates rather than dupes.
# --------------------------------------------------------------------------- #

def _hash_id(s: str) -> int:
    """Deterministic 31-bit int from a string (Anki id range)."""
    h = hashlib.sha1(s.encode('utf-8')).hexdigest()
    return int(h[:8], 16) % (1 << 31)


# --------------------------------------------------------------------------- #
# Anki models — concept (with reversed template) + cloze.
# --------------------------------------------------------------------------- #

CSS = """
:root {
  --bg:#fff; --text:#37352f; --title:#37352f; --num:#9b9a97;
  --bullet:#b3b2af; --onum:#9b9a97; --divider:#ededed; --muted:#787774;
}
.night_mode {
  --bg:#191919; --text:#e6e6e6; --title:#fff; --num:#9b9a97;
  --bullet:#6f6e69; --onum:#9b9a97; --divider:#2f2f2f; --muted:#9b9a97;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#191919; --text:#e6e6e6; --title:#fff; --num:#9b9a97;
    --bullet:#6f6e69; --onum:#9b9a97; --divider:#2f2f2f; --muted:#9b9a97;
  }
}
.card {
  font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI',
               'Helvetica Neue', Arial, sans-serif;
  font-size:16px; line-height:1.6; color:var(--text);
  background:var(--bg); text-align:left;
}
.front { padding:4px 0 0; }
.num { font-size:11px; color:var(--num); letter-spacing:.06em;
       text-transform:uppercase; font-weight:500; margin-bottom:6px; }
.title { font-size:26px; font-weight:700; color:var(--title);
         line-height:1.25; letter-spacing:-0.01em; }
hr { border:0; border-top:1px solid var(--divider); margin:18px 0; }
ul, ol { margin:2px 0; padding-left:28px; }
ul li::marker { color:var(--bullet); }
ol li::marker { color:var(--onum); font-variant-numeric:tabular-nums; }
li { margin:1px 0; padding-left:2px; }
p { margin:4px 0; }
p.sub { margin:16px 0 2px; }
p.sub b, b, strong { color:var(--title); }
em { color:var(--muted); }
.typehint { font-size:13px; color:var(--muted); margin:10px 0 0; }
.hint { font-size:14px; color:var(--muted); margin:12px 0 0;
        white-space:pre-line; border-left:2px solid var(--divider); padding-left:12px; }
.cloze { font-weight:700; color:var(--title); }
"""

CONCEPT_TEMPLATES = [
    {
        'name': 'Front → Back',
        'qfmt': '<div class="front">{{Front}}</div>'
                '{{#Hint}}<div class="hintlink">{{hint:Hint}}</div>{{/Hint}}',
        'afmt': '{{Front}}<hr id="answer">{{Back}}'
                '{{#Hint}}<div class="hintlink">{{hint:Hint}}</div>{{/Hint}}',
    },
    {
        'name': 'Back → Front',
        'qfmt': '{{Back}}',
        'afmt': '{{Back}}<hr id="answer">{{Front}}',
    },
]

CLOZE_TEMPLATE = [{
    'name': 'Cloze',
    'qfmt': '{{cloze:Text}}'
            '{{#Hint}}<div class="hintlink">{{hint:Hint}}</div>{{/Hint}}',
    'afmt': '{{cloze:Text}}<hr id="answer">{{Extra}}'
            '{{#Hint}}<div class="hintlink">{{hint:Hint}}</div>{{/Hint}}',
}]


def make_concept_model(tag_ns: str):
    import genanki
    mid = _hash_id('flashcards:concept:' + tag_ns)
    return genanki.Model(
        mid, tag_ns + ' :: Concept',
        fields=[{'name': 'Front'}, {'name': 'Hint'}, {'name': 'Back'}],
        templates=CONCEPT_TEMPLATES, css=CSS)


def make_cloze_model(tag_ns: str):
    import genanki
    mid = _hash_id('flashcards:cloze:' + tag_ns)
    return genanki.Model(
        mid, tag_ns + ' :: Cloze',
        fields=[{'name': 'Text'}, {'name': 'Extra'}, {'name': 'Hint'}],
        templates=CLOZE_TEMPLATE, css=CSS,
        model_type=genanki.Model.CLOZE)


def render_front(front_text: str, hint_type: str) -> str:
    """Wrap front text + optional type-hint line in styled HTML."""
    t = html.escape(front_text or '')
    th = (f'<p class="typehint">{html.escape(hint_type)}</p>') if hint_type else ''
    return f'<div class="front"><div class="title">{t}</div>{th}</div>'


# --------------------------------------------------------------------------- #
# Build pipelines.
# --------------------------------------------------------------------------- #

def build_markdown(cards: list, out_path: str, deck_name: str):
    """Write a single Markdown file: ## Deck::Subdeck headers, ### per card."""
    # group by deck (preserve first-seen order)
    order, grouped = [], {}
    for c in cards:
        d = c.get('deck') or deck_name
        if d not in grouped:
            grouped[d] = []
            order.append(d)
        grouped[d].append(c)

    lines = [f'# {deck_name}', '',
             f'> {len(cards)} cards across {len(order)} deck(s)', '', '---', '']
    for d in order:
        lines.append(f'## {d}')
        lines.append('')
        for c in grouped[d]:
            ctype = c.get('type', 'concept')
            if ctype == 'cloze':
                heading = c.get('cloze', '')[:60] + ('…' if len(c.get('cloze', '')) > 60 else '')
                lines.append(f'### {c["id"]}')
                lines.append('')
                lines.append(c.get('cloze', ''))
            else:
                lines.append(f'### {c["id"]} — {c.get("front", "")}')
                lines.append('')
                lines.append(f'**A:**')
                lines.append(body_to_markdown(c.get('back', '')))
            h = c.get('hint') or {}
            if h.get('type'):
                lines.append('')
                lines.append(f'> Type: {h["type"]}' +
                             (f'\n>\n> {h["landmarks"].replace(chr(10), chr(10)+"> ")}' if h.get('landmarks') else ''))
            tg = c.get('tags')
            if tg:
                lines.append('')
                lines.append(f'<sub>{", ".join(tg)}</sub>')
            lines.append('')
        lines.append('---')
        lines.append('')

    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    return out_path


def build_apkg(cards: list, out_path: str, deck_name: str, tag_ns: str):
    import genanki
    concept_model = make_concept_model(tag_ns)
    cloze_model = make_cloze_model(tag_ns)

    # one deck per unique deck string; nested via '::'
    decks = {}
    def get_deck(deck_str):
        if deck_str not in decks:
            full = f'{deck_name}::{deck_str}' if deck_str and deck_str != deck_name else deck_name
            decks[deck_str] = genanki.Deck(_hash_id('deck:' + full), full)
        return decks[deck_str]

    def ns_tag(t):
        return t if '::' in t or t == tag_ns else f'{tag_ns}::{t}'

    counts = {'concept': 0, 'cloze': 0, 'reversed': 0}
    for c in cards:
        ctype = c.get('type', 'concept')
        hint = c.get('hint') or {}
        hint_field = html.escape(hint.get('landmarks', '')) if hint.get('landmarks') else ''
        deck = get_deck(c.get('deck') or deck_name)
        tags = [ns_tag(t) for t in (c.get('tags') or [])]
        if tag_ns not in tags:
            tags.append(tag_ns)

        if ctype == 'cloze':
            front = render_front(c.get('cloze', ''), hint.get('type', ''))
            note = genanki.Note(
                model=cloze_model,
                fields=[c.get('cloze', ''), c.get('extra', ''), hint_field],
                tags=tags, guid=genanki.guid_for(_hash_id(c['id'])))
            counts['cloze'] += 1
        else:
            front = render_front(c.get('front', ''), hint.get('type', ''))
            back_html = body_to_html(c.get('back', '')) or '<p><i>(no content)</i></p>'
            note = genanki.Note(
                model=concept_model,
                fields=[front, hint_field, back_html],
                tags=tags, guid=genanki.guid_for(_hash_id(c['id'])))
            counts[ctype if ctype in counts else 'concept'] += 1
        deck.add_note(note)

    genanki.Package(list(decks.values())).write_to_file(out_path)
    return counts, len(decks)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description='Build flashcards (Markdown / Anki) from cards.json')
    ap.add_argument('cards_json', help='path to cards.json')
    ap.add_argument('--out', required=True, help='output path (extension sets file; for md,apkg use a stem)')
    ap.add_argument('--format', default='apkg',
                    help='md | apkg | md,apkg (default apkg)')
    ap.add_argument('--deck-name', default='Flashcards',
                    help='parent deck name (default "Flashcards")')
    ap.add_argument('--tag-ns', default=None,
                    help='tag namespace (default: derived from --deck-name)')
    ap.add_argument('--hints-json', default=None,
                    help='optional separate hints.json keyed by card id (merged in)')
    args = ap.parse_args()

    tag_ns = args.tag_ns or re.sub(r'[^a-zA-Z0-9]+', '_', args.deck_name).strip('_')

    with open(args.cards_json) as f:
        cards = json.load(f)

    # merge external hints if provided
    if args.hints_json:
        with open(args.hints_json) as f:
            ext = {k: v for k, v in json.load(f).items() if k != '_meta'}
        for c in cards:
            if c['id'] in ext:
                c['hint'] = ext[c['id']]

    # validate minimal schema
    for c in cards:
        if 'id' not in c:
            sys.exit(f"ERROR: card missing 'id': {json.dumps(c)[:80]}")
        if 'deck' not in c and not args.deck_name:
            sys.exit(f"ERROR: card {c['id']} missing 'deck'")
        c.setdefault('type', 'concept')

    fmts = [f.strip() for f in args.format.split(',')]
    for fmt in fmts:
        if fmt == 'md':
            out = args.out if args.out.endswith('.md') else args.out + '.md'
            build_markdown(cards, out, args.deck_name)
            print(f'✓ Markdown: {out}  ({len(cards)} cards)')
        elif fmt == 'apkg':
            out = args.out if args.out.endswith('.apkg') else args.out + '.apkg'
            counts, ndecks = build_apkg(cards, out, args.deck_name, tag_ns)
            print(f'✓ Anki: {out}  ({sum(counts.values())} notes, {ndecks} deck(s) '
                  f'[concept {counts["concept"]}, cloze {counts["cloze"]}, reversed {counts["reversed"]}])')
        else:
            sys.exit(f"ERROR: unknown format '{fmt}' (use md, apkg, or md,apkg)")


if __name__ == '__main__':
    main()
