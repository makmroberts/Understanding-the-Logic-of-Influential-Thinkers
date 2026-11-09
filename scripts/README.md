# Source extraction

Scripts for turning public source material into annotation-ready Markdown.
Outputs go to `internal/`, which is gitignored — text stays local, only the
scripts are versioned.

## Current scope

Parsers live in `parsers/`, one per source, over the shared `parsers/common.py`.
Extractors live in `extractors/` and read only the text the parsers write.
Before 2026-11-09 these were `cfr_extract.py`, `substack_extract.py`,
`extract_lib.py` and `extract_metadata.py`, and older notes below use those names.

`parsers/cfr.py` handles CFR "Follow the Money" articles (Brad Setser).
`sources_followthemoney.csv` is the registry of the 20 articles the team is
annotating, with the per-owner year assignment.

```bash
python scripts/parsers/cfr.py --owner sicheng      # 2020 + 2024 set
python scripts/parsers/cfr.py --year 2020
python scripts/parsers/cfr.py --all                # all 20
python scripts/parsers/cfr.py --url https://www.cfr.org/articles/<slug>
python scripts/parsers/cfr.py --owner sicheng --no-cache   # force refetch
```

Output: one `YYYY-MM-DD_<slug>.md` per article in `internal/extracted/`, plus
`_manifest.csv`. Raw HTML is cached in `internal/.cache_html/` so re-runs do
not re-hit CFR.

## Verified working (2026-09-30)

Ran against all 7 articles in the 2020/2024 set. All 7 succeeded, 951–2007
words each, first and last paragraph checked by hand against the live pages.

| What | How | Notes |
|---|---|---|
| Fetch | `urllib` + browser UA | No 403, no JS rendering needed, no auth. Server-rendered HTML contains the full body. |
| Body | `<p class="rich-text ...">` | The only selector needed. Catches body text and the trailing footnotes; picks up no nav or boilerplate. |
| Metadata | JSON-LD in the `parsely-*` script tag | Gives headline, author, `datePublished`, `dateModified`, `articleSection`. |
| Inline citations | `<a>` inside body paragraphs, kept as Markdown | Essential — Setser argues by hyperlink, so the cited paper is the evidence node. |
| Figures | `<figure><img src>` on `static.cfr.org` | The **filename is usually the chart title**, URL-decoded. No `<figcaption>` exists, so this is the only caption source. |

Dependencies: Python stdlib only. `bs4`, `lxml`, and `trafilatura` are not
installed in this environment, which is why the parser is regex-based.

## Subject facets

The role axis (`schema_map.yaml`) says what a node *does* in an argument. The
subject axis says what it is *about*, so a question on one topic does not have
to read all 358 nodes.

- `facets.yaml` — the closed vocabulary. 89 terms over five facets: `variable`,
  `geo` (split into subject/counterpart, which is how "bilateral" is expressed),
  `instrument`, `data_basis`, `sector`.
- `competency_questions.yaml` — the ten question shapes that **govern** the
  vocabulary. A term is admitted only if some question needs it to
  discriminate. The `example` blocks are hand-verified fixtures and double as
  the regression suite.
- `label_facets.py` — assigns terms to nodes.

```bash
python scripts/label_facets.py --dry-run --docs setser_aug_14_24   # no API call
python scripts/label_facets.py --limit-docs 2                      # cheap trial
python scripts/label_facets.py                                     # label all
python scripts/label_facets.py --report                            # distribution audit
python scripts/label_facets.py --eval                              # score vs fixtures
```

Output: `data/node_facets.csv` (one row per node/facet/value, with a `source`
column) and `data/review_facets.md` for everything it could not map. Responses
are cached in `internal/.cache_facets/`, same as the HTML cache.

Three properties worth keeping if this is ever rewritten:

1. **The vocabulary is closed, structurally.** Allowed values are compiled into
   a JSON-schema enum built from `facets.yaml` at runtime, so the model cannot
   return a term that is not in the file and the schema cannot drift from it.
2. **One call per document, all its nodes together.** Many nodes are elliptical
   and only make sense in context — `setser_aug_14_24#SC` ("the methodology was
   already changed at a convenient moment in 2015") is a balance-of-payments
   claim that never says so. This is why the labeller is a model, not a regex.
3. **Hand beats model.** Rows with `source: hand` are never overwritten, not
   even by `--force`.

### Verified working (2026-10-15)

| What | Status |
|---|---|
| Vocabulary | 89 terms; **zero unattested** — every term matches at least one node under word-boundary matching |
| CQ cross-refs | Facet `cq:` lists and question `facets:` agree in both directions |
| Fixtures | All 50 `must_return` / `must_not_return` node refs resolve against `data/nodes.csv` |
| `--dry-run` | ~2,900 input tokens per document, ~2,350 of it the cacheable vocabulary prefix |
| `--report` | Distribution + saturation audit, flags any term over the 0.40 threshold |
| `--eval` | Scores strict and one-hop-expanded recall separately; reports `must_not_return` leaks |
| Skip / `--force` / hand rows | Tested: re-run skips labelled docs, `--force` drops only `llm` rows, hand rows survive and shadow new model rows |
| Real labelling run | all 20 docs, 359 nodes, 1,548 assignments, **0 review issues** — no invalid terms, no cardinality violations, no node needing variable inheritance |
| Fixture recall | **40/47 (85%) strict, 41/47 (87%) expanded** across all 20 docs, 0 `must_not_return` leaks — see the contamination caveat |

**Regex baseline: 15% strict / 17% expanded recall, 0 leaks.** Measured by
feeding `validate()` labels from naive word-boundary `aka` matching instead of
the model. This is the number the labeller has to beat, and it confirms the
eval discriminates rather than passing anything. It also quantifies the case
for rule 2 above: pattern matching misses nearly every elliptical node.

**The first 100% did not generalise.** An early run labelled 2 documents and
scored 15/15 on the fixtures those documents covered. Across all 20 it is
**40/47 strict, 41/47 expanded**. The 7 remaining misses are honest labelling
disagreements, not bugs — e.g. `setser_sep_20_19#P3` ("excess saving generates
surplus pressure") was labelled `geo: global` because that is what the claim
says, while CQ1 expects it under `geo: china`; it is reachable only by one-hop
expansion from the China mechanisms it feeds. Either the label or the fixture
should move, and that is a judgement call for a human.

**And the measurement is still not clean.** The labels for those two documents
were produced by a model session that could read `competency_questions.yaml`,
and the same session wrote those fixtures. So it
is the labeller grading against its own answer key. What the run does
establish: the pipeline works end to end, the vocabulary is sufficient to
express every fixture, and the labels are internally consistent. What it does
*not* establish is what an uncontaminated labeller would score. For that,
either label with a process that cannot see the fixtures, or add fixtures
after labelling. Treat 15% (regex) as the floor and 100% as not yet a result.

**What the two documents were chosen to test.** They are the two the regex
baseline failed hardest on — `setser_jun_14_19` (bilateral + sector: 0/4 and
0/5) and `setser_aug_14_24` (measurement critique: 1/7). Both now score full
recall. The sharpest single result is CQ6: its five nodes carry *identical*
`geo` and overlapping `variable`, and are separated only by `data_basis`
(customs vs. balance-of-payments vs. enterprise-reporting). That is the facet
no general framework would have suggested, doing the work it was added for.

Bilateral encoding also behaves: 19 of 39 nodes carry a `geo_counterpart`, all
19 in the bilateral article and none in the single-country measurement article.

**No API key needed.** `--import-json` ingests the same payload the API would
return, through the same validation, caps, inheritance and provenance. An
assistant subscription is **not** API access, so this is the route when there
is no key — the two-document run above went this way,
with the payload kept in `internal/` alongside the other local artifacts.

**SDK note.** The installed `anthropic` is 0.34.2 (2024) and is broken —
`httpx` and `anyio` are missing, so it does not import. It also predates
structured outputs. Before the first API-backed run:

```bash
pip install -U anthropic
```

`label_facets.py` targets the current API (`claude-opus-5`, adaptive thinking,
`output_config.format`) and exits with that instruction rather than a stack
trace if the SDK is too old.

### Known gaps

- **`aka` forms need word boundaries.** Nineteen are three characters or
  fewer. Substring matching is nonsense on them: `ev` hits 42 nodes via "even",
  "revenue" and "level" while matching zero real words, and `us` hits 175 via
  "surplus", "because" and "thus" against a true count of 64. The labeller
  never reads `aka` (it reads `def`), so this only bites a regex pre-pass.
- **Saturation needs a fuller corpus.** On the two-document run
  `export-volumes` (44%) and `current-account` (41%) trip the 0.40 threshold.
  That is an artifact of labelling two single-topic articles, not real
  saturation — re-read it once more documents are in.
- **`variable` inheritance is untested.** All 39 nodes got a variable
  directly, so the inheritance path has not run on real labels yet.
- **`variable` inheritance is a guess.** Nodes the model leaves without a
  variable inherit their document's two most common ones, marked
  `source: inherited` and listed in the review file. Audit those by hand.
- **`concepts.yaml` is still 9 of 358 nodes.** Facet filtering buys a constant
  factor; concept-level dedup is what makes cost flat as the corpus grows.
  That remains the larger win.

## Signed edges and graph indices

`graph_indices.py` does the two things the causal-map literature prescribes
that we were citing but not doing.

```bash
python scripts/graph_indices.py            # write artifacts + report
python scripts/graph_indices.py --print    # also dump the report
```

Writes `data/edges_signed.csv`, `data/variable_map.csv`,
`data/graph_indices.json`, and the report at `data/graph_indices.md`.
`export_obsidian.py` picks up the JSON and puts each term's graph position on
its subject hub note.

**Axelrod (1976) — explicit signs.** Every edge gets +1 (backs), -1 (pushes
back) or 0. The parser's `polarity` column already determined this perfectly —
no edge type mixes polarities — so the table only makes it numeric and
summable. 271 supporting, 67 attacking, 2 neutral: **20% of his edges push
back**, which is the size of the concede-something habit, measured.

`defers` is 0 rather than -1 deliberately: setting a question aside for a
future post neither backs nor attacks, and scoring it as an attack would
overstate how much he concedes.

**The sign is argumentative, not causal.** It means *backs* / *pushes back on*,
not *increases* / *decreases*. Axelrod signed causal assertions between
variables; our edges are support/attack between claims. Conflating the two
would be a category error, and it is the first thing to get wrong here.

**Özesmi & Özesmi (2004) — indices.** Density, in/out degree, centrality,
transmitter/receiver character, MacDonald's hierarchy index — per article,
corpus-wide, and per facet term.

| | this corpus | Özesmi & Özesmi |
|---|---|---|
| variables per map | 17.9 ± 3.9 | 23 ± 2 |
| connections per map | 17.0 ± 3.5 | 37 ± 3 |

Comparable in size, roughly half as densely connected — the expected signature
of an argument map against an elicited FCM, which closes feedback loops where
these deliberately do not.

### The finding worth keeping

`customs` runs 45 out / 21 in (bias **+0.36**); `balance-of-payments` runs 34
out / 33 in (bias **+0.01**). He argues **from** customs data and **about**
balance-of-payments data. Customs is a premise he never defends; BoP is a
contested object. That is his measurement-critique stance falling out of graph
structure rather than being asserted — and it is the strongest evidence that
`data_basis` earned its place, since no other facet separates those claims.

Also: `trade-agreements` at **-1.0** (0 out, 3 in) — trade deals are only ever
something he argues toward, never a premise he reasons from. And
`global-imbalances` at -0.27 against `manufacturing-trade-balance` at +0.11:
he argues from the manufacturing surplus toward global imbalances, which is
the March 2024 argument in one number.

### Two things not to misread

- **Hierarchy index ~0.025 does not mean the maps are flat.** MacDonald's h
  normalises by N³ while the variance it sums grows with N, so it approaches 1
  only for a *star* — one node with outdegree near N-1. It measures star-ness,
  not layeredness. Peak outdegree here is about 4 of a possible 16, so near-zero
  is correct. (An earlier draft of this script predicted the opposite; it was
  wrong.) The variable-level map scores 0.56, where a few variables genuinely
  do dominate.
- **`transmitter_bias` washes out for ubiquitous terms.** `us`, `china`,
  `tariffs`, `import-volumes` sit on both ends of most edges and land near 0,
  where the number says nothing. Read bias for mid- and low-frequency terms,
  centrality for the common ones.

### Known gaps

- **The variable map is a projection, not a causal model.** A true Axelrod map
  needs the direction of effect *between variables* — "weak domestic demand
  raises the surplus" — and that sign lives in mechanism prose, unannotated.
  Adding `causal_sign` to mechanism nodes is the next annotation pass, and it
  is what would let the graph answer "if saving rises, what happens to the
  surplus?"
- **Nothing here is Kosko.** Fuzzy cognitive maps need edge *weights* to run as
  a dynamical system. We have none and will not invent them. Sign-only is what
  Axelrod's original was.
- **19 isolated nodes, all `question` nodes** — the known mermaid `~~~`
  artifact. Not a data problem, but every map's question node is unreachable by
  traversal.
- **Bidirectional pairs in the variable map** (`import-volumes` →
  `goods-trade-balance` 18, and the reverse 17) are an artifact of projecting
  argument chains, not evidence of feedback.

## Traceability

`trace.py` makes the chain from any claim back to its source visible, and
audits how much of the corpus actually has one.

```bash
python scripts/trace.py setser_aug_14_24#P2   # one claim, full chain
python scripts/trace.py --audit               # corpus-wide report
python scripts/trace.py --match-urls          # re-solve the URL join
```

The chain has six links, and each needs its own provenance:

| link | coverage |
|---|---|
| claim → authored map line | **358/358** (100%) — every node locatable in `mermaid_code/*.mmd` |
| claim type | **336/358** READ from the map (94%); 22 inferred by keyword |
| edge relation | **139/340** READ from a label (41%); **201 inferred** |
| article → published URL | **20/20** articles, all verified by opening the page; 358/358 claims reach one (100%) |
| article → passage | **69/359 anchored (19%)**, 270 candidate, 20 unlinked |
| claim → subject facets | 358/358, each with `source` and `model` |

Every claim note now states its own provenance: the authored map, whether the
article has a URL at all, whether its type was read or inferred, and the
`trace.py` command for the full chain.

### What this fixed

**Inferred edges were invisible.** 201 of 340 edges carry no label in the
source map and were defaulted by `schema_map.yaml` — and the vault rendered
them identically to the 139 read off the page. They now carry
`_(relation inferred - unlabelled in the map)_`, 402 markers across the notes
(201 × 2, once in each direction). Before this, 59% of the graph's relations
looked like claims about what the author wrote when they were claims about what
the pipeline assumed.

### What is still broken, honestly

**1. Article URLs: 5/20 → 20/20, claims reaching a source 20% → 100%.**

The `plain` and `banner` maps carry no `%% url:` comment, so the parser had a
URL for only the five `meta` maps. All 20 URLs sit in
`sources_followthemoney.csv`, and the relation is 1-1 — but matching each map
*independently* fails, because the registry's `date_label` is month-granular
and wrong in three places, and `plain`-family titles are the annotator's
*question* rather than the headline.

Solving it as **one 1-1 assignment** over all 20 does work. `--match-urls`
runs a Hungarian assignment weighting title similarity 3× against date
agreement 1× (a headline shares vocabulary with the question even when
paraphrased; a wrong date is simply wrong), and prints the evidence per pair:

```
setser_dec_15_17   2017-12-15  June 2018   0.67  0.00   0.83  strong - title
                   -> Why Trade Balance Still Matters
setser_aug_13_19   2019-08-13  Aug 2019    0.20  1.00  -0.10  strong - date + subject
                   -> When It Comes to Exporting Manufactures Europe Is Now the One from Mars
```

**14 of 15 carried by direct evidence; 1 by elimination alone.** The solver
reads `%% url:` from the `.mmd` files rather than from `documents.csv`, so it
never consumes its own output and stays reproducible.

The confirmed result lives in **`scripts/source_urls.yaml`**, hand-maintainable
beside `schema_map.yaml` and `concepts.yaml`, with an `evidence:` note on every
line so any match can be challenged without re-running anything.
`parse_maps.py` reads it as an overlay — the map's own `%% url:` always wins,
so a map that later gains one silently takes precedence.

Three registry dates are wrong, and the map dates (from filenames, day-precise)
are authoritative: "Why Trade Balance Still Matters" (June 2018 → 2017-12-15),
"Why Didn't Tariffs Push Up the Dollar?" (July 2024 → 2025-05-05, already in
Known issues), and the third is the open case below.

### Verified by opening every page

```bash
python scripts/verify_urls.py        # -> data/url_verification.md
```

Reuses `parsers/common.py`'s fetch and JSON-LD parsing (so it shares the
`internal/.cache_html/` cache) and compares each page's own `headline` and
`datePublished` against what the overlay asserts.

**20 of 20 confirmed, every published date matching the map's filename date
exactly.** So the map filenames are a reliable date source and the registry is
not: three of its `date_label`s are wrong and none of the maps' dates are.

That settled the one entry that had been assigned by elimination.
`setser_may_10_19` → "What a Difference a Week (or a Weekend) Makes",
datePublished **2019-05-10**. Real article, right date, promoted out of
`needs_review`.

### What opening the pages found instead — now fixed

A worse problem, and one no amount of matching would have caught:
**`setser_may_2_19`'s map did not describe its article.**

The two May 2019 maps are byte-identical, and the content belongs to the May
10 article, not the May 2 one:

| | May 2 — "China Never Stopped Managing its Trade" | May 10 — "What a Difference a Week (or a Weekend) Makes" |
|---|---|---|
| "yuan" | **0** | **17** |
| "deprecia…" | 0 | 7 |
| "reserves" | 0 | 5 |
| "currency" | 2 | 9 |

Both maps ask "will China keep the yuan stable or let it weaken?" and both are
full of reserves, capital controls and depreciation-offsetting-tariffs. That is
the May 10 article. The May 2 article is about managed trade and purchase
commitments and never says "yuan".

So 23 claims were attributed to an article that does not make them, and
"China Never Stopped Managing its Trade" was effectively unmapped.

**`mermaid_code/setser_may_2_19.mmd` has been rebuilt from that article's own
text** — state control of import demand, the sector-by-sector buyer audit
(aircraft, soybeans, oil and gas, autos as the exception), and the
revocability critique that is his actual objection to a purchase deal:
*"if it can be negotiated by government fiat, it can be taken away by
government fiat."* The yuan argument is untouched and still lives in
`setser_may_10_19`.

| | before | after |
|---|---|---|
| duplicate maps | 1 pair | **0** |
| corpus nodes | 358 | 359 |
| edges READ from a label | 139/340 (41%) | **161/344 (47%)** |
| this map's edges labelled | — | **26/26 (100%)** |

Every edge in the new map carries an explicit relation label, which is why
corpus edge provenance rose six points: authoring a map is the one moment you
can stop an inferred relation from existing.

**It is the only model-authored map in the corpus, and that is recorded as
such** — a header comment in the `.mmd` where an annotator will see it, an
`annotation_provenance:` field in `source_urls.yaml`, an *ANNOTATION
PROVENANCE* block in `trace.py`, and an `[!info]` callout on all 24 claim
notes. Every other map was hand-built; this one still needs a human pass.

Re-annotating also exposed a vocabulary gap: `geo` had no `canada` or
`australia`, though the article's two sharpest pieces of evidence are China
shutting down Canadian canola and Australian coal with no tariff at all. Both
terms were added, with the reasoning recorded inline.

**2. Passages: 0 → 69 anchored, via two tiers rather than one.**

```bash
python scripts/parsers/cfr.py --all           # now possible: all 20 URLs known
python scripts/link_passages.py               # -> data/passage_report.md
python scripts/link_passages.py --show setser_aug_14_24#RC
```

Verifying the URLs unlocked this: `cfr_extract.py` could only reach 5 articles
before, and now extracts all 20 — **686 paragraphs**, each with a `<!-- pN -->`
anchor, exactly as the Current scope section intended.

A node's text is the annotator's *paraphrase*, so no string match finds it, and
a semantic match presented as a citation is worse than none. So links are
**graded, and the grade is part of the data**:

| grade | n | what it means |
|---|---|---|
| `anchored` | **69 (19%)** | The claim and the paragraph share a distinctive literal — a figure, a rare proper noun. The shared literal *is* the evidence and a human confirms it at a glance. **This is provenance.** |
| `candidate` | 270 (75%) | Semantic overlap only. A reviewing aid that says "start here". **Not a citation, and never rendered as one.** |
| `none` | 20 (6%) | Nothing matched. |

A literal only counts if it is *rare in that article* — "china", "imf" and
"gdp" appear in most paragraphs and discriminate nothing. An early version
skipped that test and produced anchors like `china` (30 times); the current
rule keeps 112 distinct anchors over 92 rows, mostly figures.

What an anchored link looks like:

```
setser_aug_14_24#RC  [reconstruction]
  Goods surplus understated by ~$300bn, over 1.5pp of GDP; true current
  account surplus close to $700bn — use the customs data

  p29  [anchored, anchors: 300billion 700billion]
    ...the goods surplus in the balance of payments is now about $300 billion
    (over 1.5 percentage points of China's GDP) smaller than it should be...
```

### The by-role pattern is a validity check on the maps

Linkability should not be uniform, and the prediction held:

| role | n | anchored | rate |
|---|---|---|---|
| `evidence_source` | 11 | 8 | **73%** |
| `evidence_data` | 66 | 32 | **48%**, and 0 unlinked |
| `mechanism` | 59 | 8 | 14% |
| `stated_assumption` | 42 | 1 | 2% |
| `hidden_assumption` | 13 | **0** | **0%** |

Evidence anchors because it cites figures and named papers. **A hidden
assumption anchors zero times — which is the correct result**: it is by
definition not stated in the article, so one that quoted the text would be
evidence it was never hidden and the type is wrong. The report flags that
inversion automatically if it ever appears. Nothing is flagged today, so the
annotation passes this test.

`stated_assumption` at 2% is not a failure: those claims *are* in the text,
just as prose without distinctive figures, so they land in `candidate`. The
grade distinction is literal-versus-semantic, not stated-versus-unstated.

### Reviewing the candidates by hand

270 claims have a candidate link, which is not a citation. `review_passages.py`
turns that into a worksheet you can work through in batches.

```bash
python scripts/review_passages.py --worksheet --priority   # 52 items, not 270
#   edit the decision: lines in internal/passage_worksheet.md
python scripts/review_passages.py --apply
python scripts/link_passages.py        # applies the decisions
python scripts/review_passages.py --status
```

**You do not have to review 270.** A candidate is labelled as not-a-citation,
so leaving one is honest rather than a debt — review is opportunistic.
`--priority` selects the 52 where a decision actually buys something, and each
item says why it is in the batch:

| tier | n | why it earns a decision |
|---|---|---|
| warrant types | 15 | `hidden_assumption`, `revised_prior`, `source_credibility`, `accounting_identity` — where the matcher is least trustworthy and the relation is the whole question |
| concept nodes | 7 | carry a concept id, so they recur across articles |
| CQ fixtures | 34 (overlapping) | a competency question *promises* to return these, so if an answer cites a passage, this is the citation a reader checks |

52 items, 26 of them in the `clear` band. The other ~220 can wait indefinitely.

**What you record is a relation, not a yes/no.** Every claim comes from
somewhere in the article; the question is *how*:

| write | relation | meaning |
|---|---|---|
| `s` | states | the paragraph says it |
| `a` | abstracts | the claim compresses or generalises the paragraph |
| `w` | presupposes | the paragraph only works if the claim is true — it is the unstated warrant. **The usual answer for a hidden assumption.** |
| `e` | elsewhere | a real prior of his, grounded in his wider work rather than this article |
| `no` | none | cannot place it |
| `p17 a` | | wrong paragraph — it is p17, relation `abstracts` |

An earlier version of this graded links quoted-or-not, which made `none` the
only possible answer for a hidden assumption. **That was wrong.** A hidden
assumption is abstracted *from* a paragraph: the annotator read it and inferred
the unstated warrant the passage needs. That paragraph is the provenance for
the inference even though it is not where the claim is said.

The matcher proposes a relation from the role type and cannot tell `abstracts`
from `presupposes` — that is the reading judgement the review exists for.

`--apply` records decisions in `scripts/passage_review.yaml`, and
`link_passages.py` treats them as final — **a human verdict is never
re-derived**, the same contract `label_facets.py` has with its `hand` source.

**Ordering is by value, not by document.** Hidden assumptions, priors and
mechanisms come first because those are the machinery `ask.py` reconstructs;
evidence comes last because it already anchors on figures. Within a role, by
`margin` — how far the chosen paragraph beat the runner-up:

| band | margin | n | what it means |
|---|---|---|---|
| `clear` | > 0.10 | 140 | one paragraph won outright; mostly quick yes/no |
| `moderate` | 0.05–0.10 | 46 | |
| `tie` | < 0.05 | 84 | the matcher is guessing — the worksheet prints the runner-up alongside, because that is the comparison you need |

**The relation is usually the interesting part.** Take
`setser_feb_26_20#P1` — "Trade balance = saving − investment. Never stated, but
the argument depends on it" — matched to p5, which argues that tariff
uncertainty cut investment and that weaker investment cuts imports. The
paragraph does not state the identity. But that chain only bears on the *trade
balance* if the identity holds, so p5 **presupposes** it: `w`, not `no`.

The worksheet is written to `internal/` because it quotes article paragraphs;
your decisions are paragraph numbers only, so those are versioned.

### A finding the relations surfaced

Three `hidden_assumption` claims reach **no paragraph in their own article**,
and all three turn out to be priors Setser carries across the corpus rather
than warrants of the article they sit in:

- `setser_aug_14_24#P2` — "Customs data is ground truth — **never argued for**,
  the whole case rests on it". The annotator already said so. And
  `data/graph_indices.md` measures the same thing from graph structure:
  `customs` runs a transmitter bias of **+0.36**, so he argues *from* it
  everywhere and defends it nowhere.
- `setser_jan_31_20#P2` — "The capacity to deliver purchases is the same
  capacity that can withdraw them". Stated almost verbatim in a *different*
  article: the May 2 2019 piece at p46, quoting Book and Scissors — "if it can
  be negotiated by government fiat, it can be taken away by government fiat".
- `setser_2025-07-28#P3` — "A trading partner's surplus drains demand from your
  economy".

That is what the `elsewhere` verdict is for, and it is an argument for the
concept layer: these three are exactly the cross-article priors
`scripts/concepts.yaml` exists to hold, and it is still at 9 of 359 nodes.

### What is still not done

- **The candidate tier is a narrowing, not a citation**, until reviewed. The
  `%% para: p7` convention in new maps would avoid the problem at source for
  anything annotated from here on.
- Every row carries the extraction's `page_sha256`. **Correction (2026-11-09):**
  this hash covers the whole page, so it changes when the article does not. Two
  pages re-fetched that day both had a new `page_sha256` and identical body text.
  Use `content_hash` from `extractors/metadata.py` to detect a changed article.
- `internal/extracted/` is gitignored, so these rows are pointers into local
  files. That is the existing convention (text stays local, derived artifacts
  are versioned), not an oversight.

**3. 22 node types inferred by keyword** (`l6_keyword`), where Level 6 nodes
all share one class and only the header distinguishes a caveat from an opposing
view. Marked in the notes; worth a human pass.

## Walking one article by hand (2026-10-28)

`worked_example.py --doc X [--out F]` writes the article-to-citation
walkthrough. Panels 1 and 3–7 come from `data/`; panel 2, the reading pass, is
hand-written in `worked_example_notes.yaml` and the script prints `WRITE ME`
rather than filling a gap. `--list` ranks the 20 articles by the share of
passage links that reach an anchor, which is the right selection rule: a small
map with good anchoring is one a reader can actually check.

The first one written is `setser_2025-07-07_china-stealth-surplus` (13 claims,
18 links, 57 labels, 7 of 16 links anchored). Doing it turned up five passage
links on that one article that a human pass should change, which is the useful
part:

- **`K` is `anchored` to p28 on the shared literal `7`** — the digit, pulled
  out of "G7". Formally distinctive, substantively nothing, and it is the main
  claim of the article. **A bare numeral should not be able to anchor a
  citation**; `link_passages.py` wants a minimum token length or a digit-only
  exclusion. Score 0.101, the lowest of the sixteen, so the number did say so.
- **`M1` is linked to the paragraph that states the mechanism's *result*
  (p25), not the mechanism (p14).** Generalisable: a mechanism node and the
  paragraph reporting its consequence share more wording than the mechanism
  and its own statement do.
- **`P2` is graded `abstracts` where `states` is right** — it is p26 with the
  hedge removed. It and `P1` are the article's two closest claim-to-sentence
  matches (0.442 and 0.694) and neither reaches an anchor, because every token
  they share with their paragraph is corpus-common. The literal test is
  conservative in the right direction, but these two are the evidence that
  `candidate` is not the same as a weak match — sometimes it is a
  near-quotation the IDF cannot see.
- **`Q` and `P3` are on the wrong paragraph** (p19 and p7; p7 and p26 are the
  better homes). `P3`'s relation, `presupposes`, is right.

Not fixed, and not fixed silently: these are verdicts for
`passage_review.yaml`, which does not exist yet despite being listed as an
overlay. Five of sixteen links wrong on a hand-check is the argument for
building it before anything quotes a link.

### The sixth finding: the relative floor discards a third of all anchors

Reading panel 7 against panel 2 turned up the one that matters. `E1` on the
stealth-surplus article is an aggregate evidence node whose text carries five
figures; `node_passages.csv` gives it three paragraphs. The missing two
clauses — *"about $400 per phone"* and *"net vehicle exports above 6 million"*
— are in the article at p16 and p3, and **both carry the distinctive figure**.

Measured by replaying the linker's own scoring (2026-10-28):

| | |
|---|---|
| anchored-qualified paragraph pairs, corpus-wide | 140 |
| written to `node_passages.csv` | 92 |
| **discarded** | **48 (34%)** |
| claims losing at least one | 31 |
| ... cut by the `[:3]` cap | 6 |
| ... cut by the `0.6 × best` floor alone | 25 |

`keep = [s for s in anchored if s[1] >= best * 0.6][:3]` is the line. **The
cap is almost never what bites; the relative floor is.**

The diagnosis, and it generalises past this one line: a relative score floor
is a *relevance* filter and it is being applied to a *provenance* signal. For
an aggregate evidence node the paragraph supplying the fifth figure will
always score low on cosine, because the claim text is dominated by the other
four — while the figure it shares is exactly as distinctive as theirs.

**But the floor is not pure loss, and this is why the fix is not to raise it.**
Classifying 28 of the 48 discards by what qualified them: 14 were bare
percentages (`#2percent`, `#10percent`, `#25percent` — a tariff rate recurring
through an article clears the `0.15 × n_paragraphs` distinctiveness cap and
identifies nothing), 3 were `!states !united` scoring as "two shared proper
nouns", 2 were `!covid-` plus the number `19`, and **9 were real figures or
named sources** (`#6million`, `#400`, `!buchheit !hagan !imf !lee`).

So the anchor test is over-permissive and the floor is silently compensating
for it. That is the same bug as `K` anchoring on the digit `7` above, seen
from the other end. **The fix is to tighten what may anchor** — exclude bare
small integers, require more than a two-token proper-noun pair for a country
name, repair the `covid-19` tokenisation — and only then let more survivors
through. Raising the floor without that would admit 19 pieces of junk to
recover 9 real ones.

### What was changed (2026-10-28)

Four changes to `link_passages.py`, in the order they matter. `--dry-run`
prints the delta against the existing CSV and writes nothing; use it first.

**1. The figure pattern had no left word boundary.** `(?<![A-Za-z0-9-])` now
precedes it, so a number is no longer read out of the middle of a name — the
`7` of "G7", the `19` of "COVID-19", the `321` of "A321". This is the `K`
finding above, and it was a plain tokenisation bug, not a threshold.

**2. Capitalised words are tested for being names.** `\b[A-Z]...` cannot tell
"Ireland" from the "External" that opens a sentence, and `!external` was
anchoring a claim about China's external position. `learn_names()` measures
how often each token is capitalised across the corpus: real names are at
0.93–1.00 (`ireland` 9/9, `china` 612/612, `apple` 14/15), sentence starts are
not (`external` 0.03, `global` 0.05). Of 1,601 tokens seen three times or
more, 84 clear the bar and 295 are capitalised only sometimes. Below three
appearances there is nothing to measure, so the word is allowed — that is what
keeps `!buchheit` (1/1).

**3. A literal must be rare at both scales, and a lone one must be rarer.**
`distinctive` was per-article only, which cannot see that "United States" is
in 15 of 21 articles. The cut was swept against five anchors known good by
hand and six known junk rather than picked:

| frac | cut | anchored rows | good kept | junk kept |
|---|---|---|---|---|
| 0.15 | 3 | 72 | 3/5 | 0/6 |
| **0.25** | **5** | **115** | **5/5** | **1/6** |
| 0.40 | 8 | 187 | 5/5 | 2/6 |

0.15 is the per-article rule reused without thinking and it throws away
`!apple !ireland` and `!belgian !treasury`. Separately, `LONE_ANCHOR_DF = 2`:
two shared literals are evidence on their own, one is evidence only when it is
unusual, so a claim and a paragraph sharing nothing but `#25percent` (5 of 21
articles) no longer anchor. The one junk survivor at 0.25 turned out not to be
junk — it re-anchored on `!bessent`.

**4. The relative floor is gone**, now that the gates above do the job it was
compensating for. `ANCHOR_MAX = 6` stays as a review trigger rather than a
filter.

Result: **382 rows → 411; anchored rows 92 → 115.** `E1` on the
stealth-surplus article now anchors to all five paragraphs its five clauses
come from.

**Claims reaching an anchor went 69 → 63, and that is the change working.**
For those six, the only anchor was a shared percentage or a numeral. `K` is
one of them and is now `none`: a main claim with no citable paragraph is the
normal case here, because the conclusion of an argument is rarely a sentence
in it.

**Still open.** A multi-word title whose component words are each common is
lost — `!external !sector !report` for the IMF's *External Sector Report* was
removed and nothing replaced it, because literals are unigrams. Phrase
detection would fix it and has not been tried. And the five passage verdicts
above are still verdicts: `passage_review.yaml` does not exist yet.

Second finding, on coverage rather than correctness. 16 of 29 paragraphs carry
no passage link, and the split matters: 4 are connective tissue, 4 illustrate a
premise the article never argues (the map puts that work in `Q`), and **8 are
argument the graph does represent but cannot cite** — p14–p16 (the SAFE/Apple
rebuttal behind `M1`), p22–p23, p18, p27, p29. A retrieval gap, not a modelling
gap, and the same gap the `%% para: pN` convention would close at source.

## Metadata from text (2026-11-09)

`extractors/metadata.py` is a separate step after the parser. A parser knows one
site's HTML and writes text. The metadata extractor reads
only that text, with no HTML, no publisher names and no model, and writes
`data/articles/<id>.json`. The record holds metadata, hashes and citation
locations. Article text stays in `internal/`.

```bash
python scripts/extractors/metadata.py --check   # audit, write nothing
python scripts/extractors/metadata.py --file internal/extracted/<file>.md
```

Run over everything in `internal/extracted/`, it also picks up the Substack post.
The records in `data/articles/` are the 20 Setser articles plus that post.

Re-fetching the post on 2026-11-09 caught an edit the page does not report: p99
and p101 had changed while `dateModified` still showed the publication date. It
is recorded as revision 2, with those two paragraphs listed.

| check, over all 21 extracted files unless stated | result |
|---|---|
| title, date, URL against each page's JSON-LD | 21/21 each |
| authors against JSON-LD (20 CFR pages; the Substack page was not compared) | 20/20 |
| citations against the original HTML, per paragraph (20 CFR, after the fixes below) | 311 of 311, none missed, none extra |
| character offsets return the link label (20 CFR, after the fixes below) | 310 of 310 labelled links; the one unlabelled link has zero width |
| second run with unchanged input | 0 written, 21 unchanged |
| same text, different `page_sha256` | stays revision 1 |
| one paragraph edited | revision 2, reports exactly that paragraph |

The HTML comparison is the independent test, because the extractor never reads
HTML. **The no-frontmatter and plain-text runs matched on 21/21 but are round
trips**: the title and byline they parse were written by our own `render()`. They
show the fallback works on this layout, not on someone else's header.

What it measured about the input, before any of this was built:

- `page_sha256` changes without the article changing, as corrected above.
- `dateModified` equals `datePublished` on all 20 CFR pages, so it cannot show
  an edit. The content hash is the only edit signal we have.
- In the article body alone, the title appears in 1 of 21 files, the author in
  2 and the date in 0. The header has to be part of the text the source extractor
  writes.
- Plain text loses citations: 333 hyperlinks in the body against 10 URLs visible
  as text. A file with no declared reference count gets
  `references_status: unknown`, never "cites nothing".
- A site-neutral paragraph reader over all `<p>`, `<li>` and heading tags found
  776 of the 794 paragraphs but 55% of what it returned was navigation. Not
  pursued, since the source extractor keeps that job.

### Source revision 2 (2026-11-09)

Fixed together from the cached pages, with no re-fetch, so the 20 CFR articles
changed once:

- **Missing text.** The selector read only `<p class="rich-text">`. Lists and
  `h4` subheads are now included: 10 paragraphs across 3 articles (686 -> 696).
  The Newsletter box stays out as boilerplate.
- **Fused words.** Spaces at the edge of a link now stay in the sentence.
- **Unlabelled link.** Kept as `[](href)`, since the author did write it.
- **Figures.** All 113 now record the paragraph they follow.
- **`retrieved_at`** is now the cached page's fetch time, not the time of the
  latest re-render.

The diff against the previous extracts showed 10 paragraphs added, 15 edited and
none removed. Three articles were renumbered: `setser_dec_15_17`,
`setser_jun_4_18` and `setser_2026-02-03_october-2025-deficit`. No human verdict
needed remapping, because `passage_review.yaml` does not exist and the worksheet
had no decisions filled in.

`link_passages.py` was re-run. Mapping old paragraph numbers to new ones, 330 of
338 linked claims kept the same link and grade. The other 8 are all in those
three articles, because the matcher now sees new text. Anchored rows went 115 ->
117; claims reaching an anchor stayed at 63.

Eleven records are now revision 2 and carry `source_changed_review_passages`.
That flag persists across re-runs until someone removes it.

The same day the record gained what the pages offered and it had been dropping:
subtitle, full publication time, programs, CFR's topic tags, license, section,
document type, language and word count. `series` was a hardcoded constant and is
now read from the page, so the October 2025 article, which is not in Follow the
Money, has none. Co-authors named in a "joint post by" opening line are added to
the byline, and `*` footnotes are labelled as footnotes. These are metadata only:
the body text and every paragraph number stayed the same.

Author titles are deliberately left out: the page shows a person's current title,
which would be wrong on an old article.

The extractor no longer imports `export_citations.py`, so it has no tie to the
old pipeline. `map_doc` was removed from the records for that reason, and parsers
no longer write an argument-map placeholder, so nothing in `parsers/` or
`extractors/` touches the Mermaid maps. The older scripts that read
`mermaid_code/` are legacy, to be retired as the annotation JSON replaces them.

The reorganization also exposed that `verify_urls.py` had been importing `fetch`
and `parse_jsonld` from a module that stopped defining them in the October split,
so it could not start. It now imports from `parsers/common.py`.

### PDF test: Pozsar's Global Money Notes (2026-11-09)

`parsers/pozsar.py` turns the 41 Credit Suisse PDFs into the same text format, and
`extractors/metadata.py` read them with no code change. That was the point of
the split. Output went to a scratch directory, not `data/articles/`.

A PDF has only positioned text, so structure is inferred from layout: line
spacing for paragraphs, font size for headings, and repeated lines for page
furniture. Words the extraction splits ("C hanges", "bil lion") are left as they
are, because repairing them would mean guessing at the text.

Known limits: link URLs and locations are exact but label edges are estimated
from character width; a paragraph interrupted by a figure or page can split in
two; some text in diagrams survives as short paragraphs; and the five earliest
notes (2015 to 2016) have no parseable author block, so they stay null and flagged.
PDF `/Author` metadata was deliberately not used: it names whoever typed the file.

Still open:

- Quoted text is not marked, and `<blockquote>` is not a reliable signal for it.
  Read by hand, CFR's 8 blockquotes are 3 quotations of the IMF's 2024 China report
  (`setser_aug_14_24` p7, p15, p31), 4 sections of Setser's own argument in
  `why-didnt-tariffs-push-us-dollar`, and 1 empty element. A curly-quote search
  finds 4 more quotations of 12 or more words inside ordinary paragraphs.
- Entities cover byline authors and the publisher only, with `entity_id` null.
  Matching names in prose needs a hand-maintained list that does not exist yet.

## Known issues

- **Date in the article list is wrong for one entry.** "Why Didn't Tariffs Push
  Up the U.S. Dollar?" is listed as July 2024 but CFR dates it **2025-05-05**.
  The extractor uses the CFR date, so the file is named `2025-05-05_...`.
  Strictly this belongs to the 2025 bucket — worth raising with the team.
- **External co-authors are partly lost.** JSON-LD does carry CFR-affiliated
  co-authors (Dylan Yalbir on "Slouching Toward Phase One", Michael Weilandt on
  "China's Record Manufacturing Surplus"). It drops non-CFR ones: Volkmar Baur
  of Union Investment is a co-author of the manufacturing-surplus post but
  appears only in the first body paragraph. Check `p1` and add by hand.
- **Figure titles degrade on some posts.** Most filenames are real chart titles
  ("U.S. Non-petrol Goods Trade..."), but the March 2024 post uses placeholders
  ("1", "second", "ToTal Man Exp"). For those, read the chart off the page.
- Regex parsing is brittle by nature. If CFR restyles the site, the
  `rich-text` selector is the first thing to check — the script prints
  `WARNING: no body paragraphs matched` rather than writing an empty file.

## Scaling up later

This is deliberately small and single-source. For the planned
large-scale extraction skill, the pieces that should generalize are:

1. **Registry-driven selection.** A CSV of `slug,url,owner,...` with
   `--owner`/`--year`/`--all` filters. Swap the CSV, keep the interface.
2. **Per-source adapter.** Only `fetch`, `P_RE`, `parse_jsonld`, and
   `figure_title` are CFR-specific. Splitting those into a source adapter
   (one per publisher: CFR, Substack, LinkedIn, Bridgewater) with a shared
   `render()` is the natural refactor.
3. **Fixed output contract.** Stage 1a in frontmatter, Stage 1b as `TODO`
   slots, body with `<!-- pN -->` anchors, then Figures and References. The
   paragraph anchors matter: argument-map nodes should be able to cite `p7`.
4. **Caching and rate limiting.** Already in place (2s delay, 3 retries,
   SHA-keyed HTML cache). Keep both when parallelizing.
5. **Manifest.** `_manifest.csv` with counts and `page_sha256` is what makes
   re-extraction auditable. Keep it.

6. **The vocabulary should be imported, not written.** Measured 2026-10-21:
   `variable`, `country` and `bloc` carry an `align:` on **every** term (53 of
   77 terms overall, 77% of all 1,450 assignments) — BPM6, SNA, ISO 3166,
   GFSM, M49, SITC, Comtrade, ISIC. `instrument` (13) and `data_basis` (11)
   carry **none**: 24 terms, 23% of assignments, minted here with no reuse
   search recorded, against the file's own `reuse before minting` rule.

   That is the only part of the chain that is hand-authored per thinker. The
   questions are not: all 11 are parameterised shapes (`What does he assume
   about {variable} in {where}?`) and **none of the 11 contains a domain
   word** — no "tariff", no "China" — so they transfer to another
   financial/economic thinker unchanged.

   The fix is not to write the 24 faster, it is to import candidates and let
   the existing gates filter them: a term survives only if it is *attested* in
   the corpus and only if some question *needs* it to discriminate. Both gates
   are already mechanical. Plausible sources to check: IMF **AREAER** (capital
   controls, FX intervention), **WTO/UNCTAD TRAINS** (trade measures), IMF and
   OECD fiscal/monetary/industrial-policy classifications for `instrument`;
   BPM6, Comtrade, SNA and SDMX source codes for `data_basis`. None has been
   checked yet — deferred 2026-10-21, not rejected.

Annotation reference lives in `internal/`: `reference/pipeline_structure.md`
(the 3-stage pipeline), `maps/` (one argument map per article), and
`maps/architecture/` (the general architecture and the side-by-side demo).

Do not add more output paths to the repo. Extracted text and caches belong in
`internal/`; anything shared with the team gets exported, not committed.
