# Annotation pipeline

Turns a published article into the same argument structure the team draws by hand, adds it
to the knowledge base in `kb/`, and measures how close it comes to the hand-drawn maps. A
fixed workflow, orchestrated with LangGraph: the model makes only judgements, and scripts do
everything else.

## Steps

The official run of each article (the models in `settings.yaml`, first run) writes to
`articles/<doc_id>/<model>/`; only these enter the knowledge base. Every other run (another model,
a repeat `_r<k>`, an oracle run `_oracle`, see Evaluation) is an experiment and writes to
`settings.yaml` `paths.experiments`, outside this folder.

| # | Step | Done by | Output |
|---|---|---|---|
| 1 | Download, number the paragraphs | script (`kb/scripts/cfr_extract.py`, unchanged) | `kb/internal/extracted/<date>_<slug>.md` |
| 2 | Boxes | model, then script: slot IDs and levels; every excerpt found word for word; every figure and name found in the article; completeness against the hand-drawn maps, with one targeted re-ask | `boxes.json` |
| 3 | Links | model, then script: drops self-links and duplicates; flags level pairs no hand-drawn link has; one re-ask for unlinked boxes | `links.json` |
| 4 | Subject facets | model, with `kb/scripts/label_facets.py`'s rules, vocabulary, schema, validation and repairs | `facets.json` |
| 5 | Check and save; second opinion on passages (`kb/scripts/link_passages.py`, unchanged) | script | `annotation.json`, plus `review.md` only if something needs a person |
| 6 | Into `kb/data` (articles without a hand-drawn map only), then `graph_indices` → `export_obsidian` → `export_canvas` → `export_obsidian` | script | the tables and the Obsidian vault |
| 7 | Compare with the hand-drawn map, where one exists | script | `evaluation.md` |

A step that fails a check goes back to the model with the problem listed, at most
`retries.format` times; a gap against the hand-drawn maps gets `retries.reask` targeted
re-asks. Both are conditional edges in the LangGraph graph (`src/annotate/pipeline.py`).
Every model call, cached or not, is recorded in `calls.jsonl`: model, parameters, prompt and
schema hashes, repeat index, request ID, tokens, cost and the raw response.

`annotation.json` follows the draft annotation contract in `proposed_architecture/` on the
team repo, plus each box's level, attributes and `reason` (the general rule the author
applies at that step). The `reason` is not yet in the knowledge-base tables: `nodes.csv` has
no column for it.

## Quality bar

1. **Same shape as the hand-mapped articles.** Same tables, columns and vocabulary. Box count
   and the roles nearly every map has come from the hand-drawn maps themselves
   (`python -m annotate profile`). Every box has an ID, a level, subject facets and a passage
   row. Fields only a hand-drawn map can have are set to `llm`.
2. **Same depth.** Figures and references are read. Evidence is gathered into one box, as the
   maps do. Hidden assumptions are looked for. A gap triggers one targeted re-ask.
3. **Traceable.** Every box lists all its supporting paragraphs and gives a verbatim excerpt
   where a paragraph states it. Every model call is recorded.
4. **Deterministic first.** The model judges; scripts number, check, save and export.
   Responses are cached, so a re-run costs nothing and gives the same answer.
5. **Config-driven.** Roles, relations and ID rules come from `config/ontology.yaml`, facets
   from `kb/scripts/facets.yaml`. All paths are relative and set in `settings.yaml`.
6. **Self-contained.** Verified team code is copied, not rewritten, and every change is listed
   below.
7. **No vector retrieval.** Notes are selected by structure: role, subject, date and links.
8. **LangGraph** for orchestration. No LangChain.
9. **Measured.** Scored against the hand-drawn maps, compared across models, cost recorded.
10. **A reason per box.** The general rule the author applies at that step.
11. **Safe.** The key lives only in an environment variable (`settings.yaml` `gateway.key_env`). The article is passed to the model as
    material, not instructions. The full article text (`kb/internal/`) and run state are
    never committed. The official runs in `articles/` are: they are the source the
    model-mapped rows of the knowledge base are rebuilt from, as `kb/mermaid_code/` is for
    the hand-drawn ones, and they quote only a sentence or two at a time, as the hand maps
    do. Their saved answers in `cache/` are committed too, so anyone can replay them.
12. **Lean.** Every step's output is used by a later step or by a person.

## Current version (2026-11-09)

- **Model:** `anthropic/claude-opus-5.5` for all three model steps, through OpenRouter. Chosen
  from 8 models in two screening rounds: no invented names or figures and the fewest retries.
  `google/gemini-4-argon` was a close second at about half the cost.
- **Rules:** `config/ontology.yaml` version 2 (the change note is in the file), with two worked
  examples (`settings.yaml` `example_articles`).
- **Where the version is recorded:** each run's `annotation.json` (`annotation.ontology.version`,
  the models and parameters of every step). The knowledge-base tables only mark these
  articles `llm`. When the ontology version changes, re-run every model-mapped article, about
  $0.2 each, so the knowledge base never mixes versions.
- **Knowledge base:** 21 hand-mapped articles and 3 model-mapped ones.
  - The hand-mapped articles are the team's 20, identical row by row to `origin/main` b327459,
    plus 2020-10-05.
  - The model-mapped ones are 2026-07-27, 2026-09-15 and 2026-10-13.

Results of the official runs. The hand-drawn map is one human reading, not a gold standard.

| | 5 practice articles | 5 held-out articles |
|---|---|---|
| hand steps found (by shared paragraph) | 63% (52%) | 57% (46%) |
| steps per article, hand range 13-24 | 24, 4 of 5 in range | 22, 4 of 5 in range |
| boxes with a word-for-word excerpt | 96% | 95% |
| fix rounds / re-asks | 0 / 0 | 0 / 0 |
| cost per article | $0.22 | $0.21 |

- The same article mapped twice: 83% of steps agree.
- No invented names or figures in 13 official runs. Every grounding warning was checked by
  hand; all were spelling variants or abbreviations.
- Four articles were read in full and broken down before any map was opened: two held-out and
  two new. The third new article was checked line by line against its text. The model maps
  covered every main step; one error was found (see Known limits).
- The three new articles were also compared with the 4 maps the predict-vs-actual skill drew
  of each. None of the skill's 216 steps is missing from the model maps; 55-73% sit at the
  same role.

Known limits:
- **Role placement.** Content is found but often sits under a neighbouring role: a scope
  choice or benchmark becomes a hidden assumption, and a policy reductio becomes an
  intermediate claim. Most unmatched hand steps have their paragraph cited by a model step at
  another level.
- **Long articles are cut finer.** 3 of 13 runs exceed 24 steps: jan_31_20 has 30, sep_20_19
  has 29 and 2026-10-13 has 28.
- **Shallow hidden assumptions.** They are often nearly stated premises rather than the deeper
  unstated one.
- **One date error, found by reading.** In 2026-10-13, step E1 says "mid-2024"; the article
  means mid-2025. The grounding check cannot catch a wrong year that occurs elsewhere in the
  text.
- **Empty document fields.** `genre`, `shape` and `topics` in `documents.csv` stay empty for
  model-mapped articles; hand maps write them in their header.
- **Small samples.** The matcher pairs about 30 of 36 boxes the way a person would, and the
  test sets are 5 + 5 articles.

## Evaluation

- One fixed box matcher (`src/annotate/evaluate.py`): same level, and a shared paragraph or
  the only box of that role on both sides; best pairs first, one to one. Each pair records
  whether it was made by a shared paragraph or by role only.
- Scores per step: boxes, links between matched boxes, facets on matched boxes.
- `--oracle` feeds the hand-drawn boxes into the links and facets steps, so those steps are
  scored on their own (each box pairs with itself; no matcher).
- Facets are compared only on boxes the hand-drawn map has facets for.
- `--repeat 1` asks the same model again, for the agreement between runs.
- Five articles in `settings.yaml` `held_out` are never used while writing prompts and are
  left out of the profile; the worked examples in the prompt (`example_articles`) are never scored.
- `python -m annotate report` re-scores every run, official and experimental, and writes
  `evaluation.md` in the experiments folder.
- The matcher was checked by hand on two articles (36 pairs): about 30 pair the same content.

## Copied from the team repo

| Copied | From | Changed |
|---|---|---|
| `kb/scripts/*`, plus `kb/mermaid_code/` and `kb/obsidian/.obsidian/` | `origin/main` b327459 | see below |
| `kb/data/node_facets.csv` | `origin/main` b327459 | none; 2020-10-05 added: labelled by the official model, ingested with `label_facets.py --import-json` |
| `kb/data/node_passages.csv` | `origin/main` b327459 | none; 2020-10-05 added with the same `link_passages.py`. Its rarity check counts every article downloaded on the machine, so a re-run elsewhere can differ in a few anchors; main's rows are kept as committed |

Changes, each marked `annotation/ tweak` in the file:

- `export_obsidian.py`: note-name limit 120 → 90. One folder deeper, 120 left about 2
  characters below the Windows 260-character path limit.
- `export_obsidian.py`: a paragraph the model cited (passage grade `llm`) is shown as such,
  and a model-mapped article names its `annotation.json` instead of a `.mmd` map.
- `label_facets.py`: `inherit_where` takes an optional list of links, so a new article is
  repaired with its own links. Default behaviour unchanged.
- `source_urls.yaml`: added `setser_2020-10-05`. The map was added on main without a URL
  entry, so it had no passages.
- `sources_followthemoney.csv`: added the same article, so `--all` downloads it.

`link_passages.py` is run unchanged for the second opinion: its input and output paths are
pointed at a temporary folder for the duration of the call.

Rebuilt here: 21 hand-mapped articles, 373 claims, 472 links. For the 20 articles in the
team's `data/`, every table matches row by row (checked 2026-11-09).

## Running

Install once (see `pyproject.toml`), then from this folder. Models are called through one
OpenAI-compatible service set in `settings.yaml` `gateway` (OpenRouter; the Duke AI Gateway is
kept there as a comment). Cached steps run offline, so the committed official runs replay
without a key and give the same output. A new article needs a key in the environment
variable `OPENROUTER_API_KEY`. Never put a key in a file.

```
python -m annotate run --url https://www.cfr.org/articles/<slug>   # a new article
python -m annotate run --doc setser_aug_14_24                       # a hand-mapped one: evaluated, not added
python -m annotate run --doc setser_aug_14_24 --model google/gemini-4-argon   # another model (an experiment)
python -m annotate run --doc setser_aug_14_24 --oracle              # links and facets on the hand-drawn boxes
python -m annotate run --doc setser_aug_14_24 --repeat 1            # ask again
python -m annotate report                                           # evaluation.md in the experiments folder
python -m annotate kb       # re-add model-mapped articles; run after parse_maps.py or link_passages.py
```

A run killed part-way (sleep, closed terminal) resumes at the step that was running
(checkpoints in `runs/`). A run that stopped on an error starts afresh next time; the steps it
finished come back from the cache at no cost.

Measured cost per article through OpenRouter: about $0.22 with Claude Opus 5.5 (the official
model), $0.13 with Gemini 4 Argon, $0.10 with GPT-6.1 Sol, $0.04 with DeepSeek V4.1 Flash.
Used-up credit stops the run with a plain message; the same command continues once it is
topped up.

The Obsidian vault in `kb/obsidian/` is rebuilt from `kb/data` at every step 6 (or by
`python -m annotate kb`). Edit the maps or the tables, never the notes: the next export
overwrites them.

Rebuilding the hand-drawn part of the knowledge base, from `kb/`:

```
python scripts/parse_maps.py       # hand-drawn maps -> data/
python scripts/cfr_extract.py --all
python scripts/link_passages.py
python -m annotate kb              # from annotation/: adds the model-mapped articles and exports
```
