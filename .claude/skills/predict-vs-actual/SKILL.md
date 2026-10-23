---
name: predict-vs-actual
description: Blind-test the argument knowledge base on an article it has not seen. Given the article's title, publication date and URL, a fresh agent predicts the argument's workflow using only notes published before that date; the article is then read and mapped onto the same skeleton; both are rendered as side-by-side mermaid charts with a scored comparison. Use when asked to predict, reconstruct or blind-test how the author would argue a new article, or to compare a predicted workflow with the actual one.
---

# Predict vs actual

Two charts on one fixed skeleton — the team's architecture in `mermaid_code/second_flow_template.mmd`:

- **A · Predicted** — what the knowledge base says he will argue, from the title alone
- **B · Actual** — what the article argues, marked against the prediction

The work splits in two. **You decide what goes in each box.** `pva.py` decides
everything else — what the predictor may see, whether the boxes follow the rules,
the layout, the colours, the score. Never write mermaid by hand; write JSON and
let the script draw it. Same JSON in, same charts out.

Every path, column name, stage, slot name and colour comes from `sources.yaml`.
If the data layout or the template changes, that file changes — not this one.

`RUN` below means `<output_dir>/<YYYY-MM-DD>_<slug>`, where the slug is the first
two or three title words, lower case, at most 20 characters — e.g.
`internal/pva/2020-10-05_record-chinese`. Keep it short: Windows refuses paths over
260 characters, and the article file name is long.

Run every command from the repository root. Needs Python 3 with PyYAML
(`pip install pyyaml`); on some systems the command is `python3`.

---

## Inputs

You need three things from the user: **title, publication date, URL.**

```
/predict-vs-actual Title of the article | 2020-10-05 | https://...
```

If any is missing, **ask**. Do not open the URL to find the title or date —
opening it before the prediction is locked spoils the test. If the user is unsure
of the date, ask them to read only the date line off the page.

If the knowledge base holds more than one author, ask which one, and pass a
`--docs` pattern in step 2 (e.g. `--docs '^setser'`).

---

## Steps

### 1 · Check the data

```bash
python ${CLAUDE_SKILL_DIR}/pva.py check
```

Stops if `sources.yaml`, the data and the team template disagree — a new slot in
the data, a renamed column, a stage or box renamed in the template. Fix
`sources.yaml`, not the data.

### 2 · Freeze

```bash
python ${CLAUDE_SKILL_DIR}/pva.py freeze --before <DATE> --title "<TITLE>" --run RUN
```

Writes `RUN/frozen.md` — every note published before the date, plus the slot types
that existed then — and `RUN/frozen.json` for the validator.

As the knowledge base grows: above `freeze.max_notes` (in `sources.yaml`) the
predictor gets the articles sharing the most words with the title, plus the most
recent few. `frozen.md` lists what was left out. The slot list always comes from
everything before the date, chosen or not.

### 3 · Predict — a fresh agent, before anything else

Spawn **one new general-purpose subagent** with the prompt in
[Predictor prompt](#predictor-prompt), filling in only `{FROZEN}`, `{TITLE}` and
`{OUT}`. Nothing else goes into that prompt.

When it returns:

```bash
python ${CLAUDE_SKILL_DIR}/pva.py validate RUN/predicted.json
```

If there are errors, send them back to the same subagent to fix — up to two rounds.
Never fix them yourself by reading anything about the article.

**Warnings are findings, not noise.** A name that appears nowhere in the frozen notes
usually means the predictor used outside knowledge. Keep the warning and report it.

**Optional — replication.** To show the prediction is not a one-off, run steps 2–4
a second time into `RUN_r2` with another fresh subagent, before step 5. Render then
reports how many slot calls the two runs share.

### 4 · Lock

```bash
python ${CLAUDE_SKILL_DIR}/pva.py lock RUN
```

Seals `predicted.json` with a hash and a timestamp. It refuses if `RUN/article/`
already exists, because that means the article was fetched first. Do not pass
`--force` unless the user agrees; the comparison then says so in bold.

### 5 · Read the article

Only now:

```bash
python scripts/cfr_extract.py --url <URL> --out RUN/article
```

This gives the article text with a `<!-- pN -->` anchor before each paragraph. For
a site the extractor does not handle, save the text yourself as
`RUN/article/<name>.md` with a `## Body` heading and an anchor before each paragraph.

**Check the date.** Compare the article's publication date (`date_published` in the
file header, or the date on the page) with the date you were given. If it is
**earlier**, stop: the frozen notes may include material from after publication, so the
test is not blind. Start again in a new run folder from step 2 with the correct date.
If it is later, carry on and mention it in the report.

### 6 · Map the actual — two passes

**Pass one, without opening `predicted.json`.** Read the whole article. Fill every
slot from what the article says. Follow [Mapping rules](#mapping-rules) and
[Writing rules](#writing-rules). This keeps the actual chart from being bent toward
the prediction. Write `RUN/actual.json` in this shape:

```json
{
  "kind": "actual",
  "article": {"title": "<title>", "date": "<YYYY-MM-DD>", "url": "<url>"},
  "summary": {"claim_type": "single | enumerated | typology | unresolved"},
  "slots": {
    "<every slot in sources.yaml>": {
      "status": "filled | implicit | absent | na",
      "why": "<optional, for absent or na, at most 12 words>",
      "items": [{"label": "<at most 12 words>", "para": ["p3", "p4"]}]
    }
  },
  "edges": [{"from": "<slot>", "to": "<slot>", "type": "<edge type>"}]
}
```

`items` only for `filled` or `implicit`; one item per slot, except `mechanism` (up to
two, each with `"kind": "economic" | "distortion"`). The second mechanism is
`mechanism#2` in edges.

**Pass two.** Now open `predicted.json`. For every box where both sides have
content, add a `verdict` — `match`, `close` or `opposite` — and a `note` saying what
was predicted (required for close and opposite). Do not change pass-one labels,
statuses or edges. Then write `summary.finding`: the one sentence a reader should
take away.

```bash
python ${CLAUDE_SKILL_DIR}/pva.py validate RUN/actual.json
```

### 7 · Render

```bash
python ${CLAUDE_SKILL_DIR}/pva.py render RUN              # add  --replicate RUN_r2  if step 3 was run twice
```

Refuses if `predicted.json` changed since the lock, or if a box has content on
both sides but no verdict. Writes:

| File | |
|---|---|
| `RUN/predicted.mmd` | chart A |
| `RUN/actual.mmd` | chart B — border colour and mark show how the prediction did |
| `RUN/legend.mmd` | one legend for both charts, only the marks that occur |
| `RUN/comparison.md` | the score, where the error travels, replication, box by box |

Both charts carry the same boxes and the same arrows in the same order — each chart
hides the other's arrows — so every box sits in the same place on both. Paste each
`.mmd` into https://mermaid.live, export PNG, place A and B side by side, the legend
underneath.

### 8 · Report

Tell the user, in plain words:

1. The **finding** — one sentence.
2. **Slots** right, split into the **free** ones (that "always yes" also gets) and the
   **real calls** (slots the article leaves empty). Only the real calls show skill.
3. **Content** — of the boxes both sides filled, how many said the same thing, and how
   many said the **opposite**.
4. **Where the error travels** — the chain of wrong boxes, starting from the first.
5. **New slots** — used by the article but not yet in the framework at the cutoff.
6. Replication agreement, if run. Anything forced, warned or contaminated.

Keep it short. Lead with the finding, not the method.

---

## Predictor prompt

Use this text exactly. Replace only the three `{…}` fields.

> You are predicting how an author will argue an article you have not seen. The
> constraints are the experiment — follow them exactly.
>
> **Read only this file:** `{FROZEN}`
>
> Do not use web search or web fetch. Do not read any other file. Use only what is in
> that file. If you find yourself reaching for something you happen to know about the
> author, the topic or the data, leave it out and mark that part as coming from the
> title.
>
> The file holds notes from the author's articles published before the cutoff.
> Each note is one move in one article, tagged with its slot. It also lists which slot
> types existed then and which edge types are allowed.
>
> **The article — title only:**
>
> > {TITLE}
>
> Predict the argument as a flow: which slots he fills, what goes in each, and how they
> connect. Write the result as JSON to `{OUT}` in exactly this shape:
>
> ```json
> {
>   "kind": "predicted",
>   "article": {"title": "<the title above>", "date": "<YYYY-MM-DD>", "url": ""},
>   "summary": {"claim_type": "single | enumerated | typology | unresolved"},
>   "slots": {
>     "<each slot type that existed before the cutoff>": {
>       "status": "filled | absent | unsure",
>       "items": [{"label": "<one short sentence>", "from": ["<note name>", "..."]}]
>     }
>   },
>   "edges": [{"from": "<slot>", "to": "<slot>", "type": "<edge type>"}]
> }
> ```
>
> Rules:
>
> - Include **every slot type the file says existed before the cutoff**, each with a
>   status. Leave out the ones that did not exist yet. A slot you expect but cannot
>   fill gets `"filled"` with an empty label.
> - `items` only for `filled`. `mechanism` takes up to two items and each needs
>   `"kind": "economic"` or `"distortion"`. Every other slot takes one.
> - `label`: at most 12 words. Start with a verb (`"Doubts…"`, `"Compares…"`); write
>   the question slot as a question. No quote marks.
> - `from`: the notes the prediction rests on, by their name exactly as the file shows
>   it. Use `"pattern"` when you expect a slot only because it recurs, and `"title"`
>   when the notes are silent and you are reading the title.
> - Read every edge as a sentence, `from <type> to`. Forward types must run to the same
>   stage or a later one. Edges may only join filled slots.
> - The date in `article.date` is the cutoff date given in the file header.
>
> Then reply with two short lists: the parts that rest on notes, and the parts that rest
> only on the title.

**Never add to this prompt.** In particular, never mention a topic, place, mechanism or
term you expect the article to contain — not even to say "don't use it". Naming it is
the leak.

Do not give the predictor anything from `examples/`.

---

## Mapping rules

How to fill the actual chart. Slot meanings are in `CODEBOOK.md` next to this file.

- **Say why, not only what.** Where the article gives the reason behind a move, put it in
  the label — "Doubts [whose] figure: [the reason]", not just "Doubts [whose] figure".
  The reason is what the knowledge base was missing.
- **Each box holds its own slot.** An opposing view is written as its holders state it;
  an other explanation as the cause itself. His response to it is the edge
  (`rebuts`, `undercut_by`), not the label.

- Fill **main_claim first**, then work backwards to what supports it.
- Every slot gets a status: `filled`, `implicit` (present but never said outright),
  `absent`, or `na` (makes no sense for this kind of piece). Never leave one out.
- **mechanism vs other_explanation.** The cause he adopts is the mechanism. A cause he
  raises but does not adopt is the other explanation. Never put the same idea in both.
- **mechanism kind.** `distortion` only when the reported number differs from what
  actually happened (coverage, timing, price adjustment, misreporting). A real event that
  hides or exaggerates a trend is `economic`.
- **claim_type.** `single` if he lands on one claim, even hedged. `unresolved` only if
  he explicitly declines to choose. `enumerated` for several parallel claims.
  `typology` when the conclusion is a classification.
- **para** on every box: the paragraph anchors it comes from.
- **verdict**, pass two only. Judge each box only on what its own slot holds; a
  difference that belongs to another slot is judged in that slot. (A conclusion that
  matches is `match` even if the reason differs — the reason is judged in the mechanism;
  say so in the note.)
  - `match` — the same claim; wording may differ.
  - `close` — the right slot, but a different claim, detail or kind, not in conflict.
  - `opposite` — the article says the reverse of the prediction (doubts the other
    side's data, blames the other cause, lands on the other conclusion).

  When unsure between `match` and `close`, choose `close`.

  A box whose prediction had no content gets no verdict — the script scores it as
  slot-only. Old files with `partial` are read as `close`, with a warning.
- **Edges** are read as a sentence, `A <type> B`:
  `main_claim rebuts opposing_view` · `main_claim qualified_by caveat` ·
  `mechanism undercut_by other_explanation`. Draw only connections the article makes.
  The script flips a pushback arrow that would point up and uses the active verb
  (`caveat qualifies main_claim`), so write the edge the way the sentence reads.
- **summary.finding** — at most 25 words, the one thing the comparison shows.

---

## Writing rules

> **This section is the one to edit to change how the charts read.**
> The word limits are in `sources.yaml` under `writing`; the script enforces them.

The reader is busy and sees both charts at once on one slide.

1. **One idea per box, at most 12 words.** If it needs two sentences, it is two slots.
2. **Start with a verb, no subject.** "Doubts the official figure" — not "He doubts…",
   not "Source credibility assessment of…". The question slot is written as a question;
   a mechanism may read as cause → effect ("[cause] pushes up [effect]").
3. **Say what he does**, not what the slot is called. The slot name is already on the box.
4. **Plain words.** Write it the way you would say it out loud. Cut any term a
   non-specialist would stop on.
5. **Quote marks only around words copied exactly from the article.** The validator
   checks every quoted phrase against the text and fails a paraphrase.
6. **At most one number**, and only the one that carries the point.
7. **No hedging words** — "perhaps", "seems", "arguably". Uncertainty goes in `status`.
8. **No internal ids** — never P1, M2, SC, E1 in visible text. The validator warns.
9. **No team member names** anywhere in the output.
10. **Notes** start with `predicted:` and say what was predicted, at most 12 words —
    "predicted: [what the prediction said]".
11. **The finding** names what was predicted and what happened, in one sentence.

---

## What the data looks like

Learned from reading the pipeline; `pva.py check` confirms it each run.

- `mermaid_code/*.mmd` is the authored source. `scripts/parse_maps.py` turns it into
  `data/nodes.csv`, `data/edges.csv` and `data/graph.json`; `scripts/export_obsidian.py`
  turns that into `obsidian/`. **Never write into `mermaid_code/`** — the parser ingests
  every `.mmd` there as a real article, so a prediction would enter the knowledge base
  as if he had written it. The script refuses.
- Node ids are local to one article. A note is named by **date and id** (`2020-07-08 Q`).
  If two articles share a date, `freeze` names those notes `doc#ID` instead, and a bare
  date-and-id citation that could mean either fails validation.
- About 60% of edges had no label in the source map and were filled in as `supports`
  by the parser. `frozen.md` marks those with `*`.
- Empty slots are dropped by the parser, so the data only holds filled ones. The JSON
  is where empty slots and their reasons live.
- Three map templates coexist (`plain`, `banner`, `meta`). They share the same stage
  ids, so stages are safe to compare across all of them.
- Some L6 notes are typed only as a generic `counterpoint` because the parser could not
  tell which kind. `check` lists them.

## When the knowledge base grows

| Change | What to do |
|---|---|
| More articles | nothing — above `freeze.max_notes` the freeze picks by title |
| A second author | pass `--docs '<pattern>'` to `freeze` |
| Two articles on one date | nothing — citations become `doc#ID` automatically |
| A new slot in the data | `check` fails; add it to a stage and to `slot_names` in `sources.yaml` |
| The team renames a stage or box | `check` fails; copy the new name into `sources.yaml` |
| A new edge type | `check` fails; add it to `forward` or `pushback` (and `reverse_label`) |
| A column renamed | `check` fails; fix `data.columns` |
| A new note field, e.g. `why` | list it in `data.show_columns`; `freeze` then shows it to the predictor |

**The agreed next data change is a `why` field** — the reason behind each move, not only
the conclusion. It is already listed in `show_columns`; `check` reports it as "not in the
data yet" until `parse_maps.py` writes it. Nothing else in the skill needs to change.

---

## When something stops

| Message | Cause | Fix |
|---|---|---|
| `check` fails | data, template and `sources.yaml` disagree | edit `sources.yaml` |
| `refusing to write under …` | output aimed at `mermaid_code/`, `data/` or `obsidian/` | use the `output_dir` |
| `… exceed the budget` | knowledge base larger than `max_notes` | pass `--title` |
| `lock` refuses | article fetched before the prediction was sealed | delete `article/`, re-predict |
| `render` refuses: changed since locked | `predicted.json` edited after the lock | restore it, or re-run from step 3 |
| `render` refuses: no verdict | pass two not finished | add `match`, `close` or `opposite` |
| `quoted … is not verbatim` | paraphrase in quote marks | drop the marks or copy the exact words |
| `citation … is not among the frozen notes` | the predictor named a note that is not there | send back to the predictor |
| `matches more than one article` | two articles share that date | cite as `doc#ID` |
| `frozen.json is from an older version` | run frozen by an older `pva.py` | re-run freeze for that run |
| `… is deep` warning | run folder path too long for Windows | shorter slug |
| `already holds a prediction` | the run folder was used by an earlier test | use a new folder, e.g. `RUN_r2` — never overwrite a test |

## Files

```
predict-vs-actual/
├── SKILL.md          this file
├── sources.yaml      where the data is, the stages, the palette, the word limits
├── pva.py            check · freeze · validate · lock · render · template · example
└── examples/         for reference — never shown to the predictor
    ├── template/
    │   └── second_flow_template.mmd    copy of the team architecture   (pva.py template)
    └── <YYYY-MM-DD>_<slug>/            one folder per finished run    (pva.py example RUN)
        ├── predicted.json / predicted.mmd
        ├── actual.json / actual.mmd
        ├── legend.mmd
        ├── comparison.md
        └── predicted.png / actual.png / legend.png    the .mmd files exported from mermaid.live
```

To keep a finished run as an example, run `pva.py example RUN` — it refuses a run
that does not validate, has a broken lock, or was not re-rendered after a JSON edit.
After the team changes the template, run `pva.py template` to refresh the copy.
