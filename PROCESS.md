# How the graph is built

## TL;DR

| #   | Step                  | What it decides                                                    | Why it is done this way                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Script                                   |
| --- | --------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| 0   | The maps              | which claims exist, what role each plays, what links them          | A role vocabulary fixed before annotation is what makes two maps comparable at all (Laukkanen 1994; Markóczy & Goldberg 1995). The stages are Toulmin's six argument elements (Toulmin 1958, as set out by the [Purdue OWL](https://owl.purdue.edu/owl/general_writing/academic_writing/historical_perspectives_on_argumentation/toulmin_argument.html)), which the Argument Interchange Format represents as information nodes (Chesñevar et al. 2006), so a second annotation scheme has something to map onto. | none — hand-drawn                        |
| 1   | Parse                 | which nodes become claims, each claim's role, each link's relation | Three role tables tried in order, so a role read from the map is never confused with one inferred.                                                                                                                                                                                                                                                                                                                                                                                                                | `parse_maps.py`                          |
| 2   | Type unlabelled links | the relation on a link the annotator did not label                 | A relation hierarchy is the standard handle on sparse, long-tail relations (Han et al. 2018).                                                                                                                                                                                                                                                                                                                                                                                                                     | `parse_maps.py`                          |
| 3   | Label the subject     | what each claim is about, from a closed vocabulary                 | Typing terms against a fixed vocabulary rather than inducing one (Babaei Giglou et al. 2023); one label for an author's many phrasings (Heddaya et al. 2024); a subject described by several independent axes combined, rather than by one place in one tree (Ranganathan 1933).                                                                                                                                                                                                                                  | `label_facets.py`                        |
| 4   | Govern the vocabulary | which terms are allowed to exist                                   | A term is admitted only when a competency question needs it to separate two answers (Grüninger & Fox 1995), paired with per-claim provenance (Nasir et al. 2026). Terms reuse a published code before minting a new one (Poveda-Villalón et al. 2022).                                                                                                                                                                                                                                                            | `competency_questions.yaml`              |
| 5   | Derive                | signs, bilateral pairs, graph indices                              | A sign on each edge and no weight: the articles never state strength of support, so a weight would be ours (Axelrod 1976, against Kosko 1986). Indices from the fuzzy-cognitive-map literature (Özesmi & Özesmi 2004).                                                                                                                                                                                                                                                                                            | `graph_indices.py`                       |
| 6   | Link passages         | which paragraph a claim came from, and how strongly                | Graded, because "is this the source?" has no yes/no answer for an unstated assumption. TF-IDF                                                                                                                                                                                                                                                                                                                                                                                                                     | `link_passages.py`                       |
| 7   | Export                | the vault people read                                              | Rebuilt from the maps on every run, so nothing a person decides may live in it.                                                                                                                                                                                                                                                                                                                                                                                                                                   | `export_obsidian.py`, `export_canvas.py` |
| 8   | Trace                 | where any single line came from                                    | Provenance for assertions a process derived rather than a person asserted (Groth, Gibson & Velterop 2010; Hernández, Hogan & Krötzsch 2015; PROV-O).                                                                                                                                                                                                                                                                                                                                                              | `trace.py`                               |

---

## The three files that hold the decisions

- `scripts/schema_map.yaml` — what counts as a claim, the three role tables, the
  relation vocabulary, the arrow defaults, the invisible-operator rules.
- `scripts/facets.yaml` — the subject vocabulary: five facets, 77 terms, each
  with a definition written to discriminate, plus the validation rules.
- `scripts/competency_questions.yaml` — the 11 questions that govern which terms
  may exist. For scale: OntoKG-EQ (Nasir et al. 2026), the exemplar for this
  pattern, governs its ontology with **five** fixed analyst questions. Eleven is
  already a looser gate than the thing it is modelled on, and the pending
  roll-up proposal would take it to fifteen, which loosens it further. The
  number is worth defending deliberately rather than letting it drift up.

Nothing in the pipeline makes a decision these files do not already contain. If
a step meets a case they do not cover, it writes the case to a review file
instead of choosing: `data/review.md` after a parse, `data/review_facets.md`
after a labelling run. Read those after any run.

---

## Step detail

### 0. The maps

One hand-drawn Mermaid flowchart per article, in `mermaid_code/`. **Code never
rewrites them.** A teammate uses them as ground truth for a separate
flowchart-prediction task, so changes to them need coordinating. Normalisation
drift is reconciled in `schema_map.yaml` instead.

Three annotation templates are in use (`plain`, `banner`, `meta`) and they put
information in different places: in `plain` maps the claim is in the bold line
and the annotator's note in the body; in the others it is reversed. Every claim
records which family it came from, and any cross-corpus count must control for
it.

### 1–2. Parsing

`parse_maps.py` reads the maps and writes `data/nodes.csv`, `data/edges.csv`
and `data/documents.csv` - the last being per-article title, date and url,
read out of each map's own title node.

Roles resolve in three tries — the bold line, then the class assignment, then
the stage the claim sits in — and each claim records which one answered. Across
the corpus that splits 148 / 188 / 23, so 336 of 359 roles are read from the map
and 23 are inferred.

Relations come from three places and each link records which: a label the
annotator wrote (161), a bare solid arrow taken as plain support (183), or the
invisible `~~~` connector (111). The support default is evidenced rather than
assumed: in the 13 maps that label selectively, all 49 written labels are
non-support, so leaving a link bare is the annotator's shorthand for support.

The 111 recovered links carry no label, so the pipeline tries to derive one from
the relations the annotator did write, backing off from the exact role pair to
the role family to the argument element. Measured leave-one-out over the 161
labelled links: 81% at the exact pair, 85% at the family, 59% at the element,
89% backing off through all three (144 of 161, 95% CI 84-93). It still types
only 3 of the 111, because
question→prior and prior→datum links carry no labelled example anywhere. The
other 108 take a declared fallback, `frames`, signed 0, so recovering that
structure cannot inflate any support count.

### 3–4. The subject axis

`label_facets.py` assigns terms from `facets.yaml` — five facets, 77 terms. All
of an article's claims go in one call with the article's question for context,
because claims are elliptical and often do not name their own subject.

The list is closed structurally: the allowed values are compiled into the
response schema from the YAML at run time, so an off-list term is a validation
failure rather than a new tag.

Why a model rather than a word search: give a word search every wording the
vocabulary lists, over the whole claim, and it reproduces 41% of the model's
1,450 labels (598, 95% CI 39-44) at 74% precision (598 of 809, CI 71-77). 59% of labels use none of the term's own wordings
anywhere in the claim.

Five rules then check the result, and two of them repair. Repaired rows are
marked `inherited` rather than read — four rows of 1,454. A repair that looks
like a reading is how a corpus stops being evidence.

### 5–6. Derived properties

Signs are a function of the relation, so no edge is signed by hand: 277 back,
111 neither, 67 push back. The sign is argumentative — _backs_ and _pushes back
on_, never _increases_ and _decreases_.

`bilateral` is one predicate: a counterpart is set. 90 claims, 14 ordered pairs,
direction preserved.

Passage links are graded. `anchored` means the claim and the paragraph share a
distinctive literal — that is provenance. `candidate` means semantic overlap
only, a narrowing from thirty paragraphs to one, and the vault never renders it
as a citation. In the vault today: 69 anchored, 270 candidate, 20 with no
passage at all.

### 7–8. Export and trace

`export_obsidian.py` writes the vault and prunes notes it no longer produces.
**Quit Obsidian first** — its autosave empties `colorGroups` in
`.obsidian/graph.json` while the export is writing it.

Any single claim can be walked back:

```
python scripts/trace.py setser_aug_14_24#P2
```

A claim is cited as `doc#node_id@map_rev`. The revision matters because
`node_id` alone is a slot address, not an identity: there are 42 distinct ids
across 359 claims, and `P1` exists in all 20 maps.

---

## How to read a claim note

The vault is what a teammate actually looks at, and three parts of a claim note
use vocabulary the maps do not contain. Worked against one note,
`claims/hidden_assumption/A correctly measured imbalance ought to drive policy`:

```
type: hidden_assumption · level: L1 · family: banner
relation_sources: [label]
variable: [current-account, global-imbalances] · country_subject: [china]
data_basis: [imf-publications]

## Leads to
- +1 licenses -> The size of the imbalance, correctly measured, must be
  factored into Chinese policymaking   `recommendation`

- Passage: p25 - proposed `presupposes`, score 0.481; unreviewed, not a citation
- Node setser_mar_10_24#P2 · type resolved by `header`
```

Read top to bottom: an unstated assumption, read from the article's bold line
rather than inferred; about China's current account and global imbalances, and
resting on IMF publications as its evidence base; it licenses one recommendation
and nothing pushes back on it. `relation_sources: [label]` says every link it has
was written by the annotator - this claim has no recovered links, so none of its
lines say `frames`.

### The relation lines

`## Leads to` and `## Rests on` list the claim's links. Each carries a relation
and a sign: **+1** backs, **0** neither, **-1** pushes back on. The sign is
argumentative, never causal - it means _backs_, not _increases_.

Eleven relations are in use. Thirty written labels normalise onto them, so
"qualifies", "limited by", "measurement caveat" and six more all become
`qualified_by`.

| sign   | relations                                                                      | count |
| ------ | ------------------------------------------------------------------------------ | ----- |
| **+1** | `supports` 248 · `licenses` 21 · `motivates` 4 · `bounds` 3 · `reconstructs` 1 | 277   |
| **0**  | `frames` 108 · `defers` 3                                                      | 111   |
| **-1** | `qualified_by` 29 · `undercut_by` 21 · `rebuts` 14 · `revises` 3               | 67    |

Two need explaining because they are not obvious:

**`frames`** is the only relation minted rather than reused. It is the declared
fallback for links recovered from the invisible `~~~` connector: the question
setting up what the article will assume is not support, licensing, bounding or
motivation, so none of the existing relations fits. It signs **0** deliberately.
An earlier version of `schema_map.yaml` typed the 65 prior-to-datum links as
`licenses` (+1), reasoning that a prior licenses a datum's relevance - plausible,
unevidenced, and it would have added 65 units of support to every corpus-wide
measurement. Sign 0 records that the structure is there without claiming a
direction. If a note shows `0 frames`, that link was recovered, not written.

**`defers`** signs 0 for the same reason: setting a question aside for a later
post is not a concession.

### The passage line

```
- Passage: p18 - proposed `presupposes`, score 0.347; unreviewed, not a citation
```

Three separate pieces of information:

- **`p18`** is the paragraph of the article.
- **`presupposes`** is the _relation between the claim and that paragraph_, from
  four values: `states` (the paragraph says it outright), `abstracts` (the claim
  generalises what the paragraph says), `presupposes` (the paragraph only works
  if the claim is true, but never says it), `elsewhere`. This vocabulary exists
  because "is this the source?" has no yes/no answer for an unstated assumption.
- **`proposed`** means the relation was inferred from the claim's role, not from
  the text. The matcher cannot distinguish `abstracts` from `presupposes`;
  `scripts/review_passages.py` is where a person settles it. **0 of 359 have
  been reviewed.** The score is text similarity, and a low one is expected for a
  claim the article never states.

The grade is carried by how the line is written, not by a label. An anchored
passage is set in bold and names the literal the claim and the paragraph share:

```
- Passage: **p7** - **states**, anchored on `10percent`, a literal the claim and the paragraph share
```

A candidate is set in italic and says so outright. The word "candidate" appears
nowhere in the vault; it is the grade's name in `data/node_passages.csv` and in
`data/passage_report.md`.

The role-to-relation pattern is also a validity check: hidden assumptions come
out `presupposes` 10 times and `states` **zero** times. One that _stated_ a
literal would mean the role is wrong, because the claim was not unstated after
all. `data/passage_report.md` has the full table.

### The last two lines

The line `type resolved by class` says which of the three role tables answered - the
bold line, the class assignment, or the stage - so a role read from the map is
never confused with one inferred. `Full chain:` gives the exact command to walk
that claim back to the map.

---

## What is computed, and how

Four places in the pipeline do arithmetic that decides something. Everywhere
else the decision comes from a declared rule or from the model.

### Passage matching: similarity ranks, a literal grades

Two independent mechanisms, and the distinction is the point - **a cosine never
promotes a link to `anchored`.**

_Ranking_ is tf-idf cosine, computed over the paragraphs of one article rather
than over the corpus, because a word that appears in every paragraph of an
article cannot tell you which paragraph a claim came from:

```
idf(w) = log(1 + N / (1 + df(w)))        N = paragraphs in this article
                                         df(w) = paragraphs containing w

cos(c, p) = SUM_w  c_w * p_w * idf(w)^2
            ---------------------------
            ||c||_idf  *  ||p||_idf
```

Raw term counts, no sublinear scaling, stopwords removed, tokens of three
letters or more.

_Grading_ is a literal-overlap test that ignores the cosine entirely. Figures
are canonicalised (`$430 billion`, `~$430bn`, `430B` all become `430billion`)
and proper nouns and acronyms are extracted. A literal only counts if it is
**distinctive in that article** - present in at most 15% of its paragraphs - so
"China", "IMF" and "GDP" are discarded while "$300bn" and "COFCO" survive.

- `anchored` - the claim and the paragraph share at least one distinctive
  figure, or at least two distinctive proper nouns. Keeps every anchored
  paragraph scoring within 60% of the best cosine, at most three.
- `candidate` - no shared literal, top cosine at or above **0.18**. Keeps one,
  and records `margin`, the gap to the runner-up.
- `none` - below the floor.

So a score of 0.481 with grade `candidate` means the paragraph is the closest
one by wording and shares no distinctive literal with the claim. A similarity of
0.9 would not change the grade. That is deliberate: similarity is a search aid,
a shared literal is evidence.

### Worked: the four numbers on one claim

`setser_mar_10_24#P2`, _"A correctly measured imbalance ought to drive policy"_,
as `data/node_passages.csv` records it:

```
para p25 · grade candidate · score 0.481 · margin 0.391 · anchors (none)
```

Four numbers doing four different jobs.

**The cosine picks which paragraph, and nothing more.** 0.481 is this claim
against every paragraph of this one article; p25 won, so p25 is what the note
records. The number is a pointer and is never consulted again.

The per-article idf is load-bearing here. Scored against the whole corpus,
"China", "surplus" and "imbalance" would dominate and the claim would match the
loudest paragraph anywhere rather than the right paragraph in its own article.
Scoped to one article those words appear in nearly every paragraph, so idf
drives their weight toward zero and what separates paragraphs is the unusual
vocabulary.

**The literal test decides whether it counts as evidence.** `anchors (none)` is
the operative field: the claim and p25 share no literal that is distinctive in
this article, so the grade is `candidate` whatever the cosine says. The grade is
what the exporter reads - `anchored` prints bold and names the shared literal,
`candidate` prints italic and says _not a citation_, and nothing in the vault
ever renders a candidate as a source. A cosine of 0.9 with no shared literal
would still be a candidate. That is the firewall: a similarity can never promote
itself into evidence.

**The margin routes a person.** 0.391 is the gap to the runner-up, which is wide,
so this lands in the `clear` band:

| band       | margin      | left | what it tells the reviewer                             |
| ---------- | ----------- | ---- | ------------------------------------------------------ |
| `clear`    | > 0.10      | 140  | one paragraph won outright - confirm or reject quickly |
| `moderate` | 0.05 - 0.10 | 46   | plausible, check it                                    |
| `tie`      | < 0.05      | 84   | the matcher is guessing - read both paragraphs         |

The arithmetic is not claiming p25 is correct. It is saying this one is cheap to
check, and flagging the 84 where it knows it cannot tell.

**Purity is the same idea one step earlier.** For a link with no written
relation, the back-off takes the mode for that role pair and purity is the
mode's share of the cell; it is stored on every derived link and below 0.60 it
raises a review item. The 81 / 85 / 89 leave-one-out figures are not consulted at
run time at all - they were measured once to justify having a back-off chain
rather than a flat rule.

**The pattern.** Every number in this section either writes a field, routes
attention, or settles a design question once and is never read again. None of
them asserts anything. The only thing that turns a paragraph into provenance is
a literal a person can see in both places, and the open number is that **0 of the
270 candidates have been reviewed**.

### Relation back-off: majority and purity

For a link with no written relation, the pipeline tallies what the annotator
used for the same role pair, counting only links that carry a written label,
and takes the mode.

The idea that a _hierarchy over relations_ is what rescues the sparse ones comes
from Han et al. (2018), who attack the same problem in distantly supervised
relation extraction: their coarse-to-fine attention operates over a relation
hierarchy and is, in their words, especially effective for long-tail relations.
The mechanism here is far simpler than theirs - a majority vote at each level,
no attention and no model - so the borrowing is the premise, not the method. **Purity is the modal share of that cell** - the count of the winning relation
divided by the number of labelled links in the cell. It answers one question:
_did the annotator use a single relation consistently for this role pair?_
Purity 1.00 means every labelled link of that pair carried the same relation;
0.87 means 13 of 15 did. It is stored as `relation_purity` on every derived
link, carried into the interchange-format export, and below **0.60** it raises a
review item.

**What purity is not, is a confidence.** It measures homogeneity and ignores
sample size entirely, and `min_examples` is **1**, so a cell resting on a single
observation scores a perfect 1.00 by construction. Measured over the 49 role
pairs that have any evidence at all:

|                                                | cells        |
| ---------------------------------------------- | ------------ |
| resting on one example (purity 1.00 trivially) | **24**       |
| two to four examples                           | 14           |
| five or more                                   | 11           |
| purity exactly 1.00                            | **44 of 49** |
| purity below the 0.60 flag                     | **0**        |

**Where the measure comes from.** Nothing in this project cites a source for
purity - it was introduced here unattributed - but the quantity is not ours. It
is the standard clustering-evaluation **purity** of Manning, Raghavan &
Schütze, _Introduction to Information Retrieval_ (2008), §16.3: assign each
cluster its majority class, then count correct assignments over N. What is
computed here is that formula applied to one cell at a time.

That matters, because the literature already names the defect measured above.
Purity rises trivially with granularity - a clustering of singletons scores
exactly 1 - so a high value says as much about how finely the space was cut as
about how coherent the groups are. Twenty-four single-example cells scoring 1.00
is that pathology, not a surprise. The textbook remedy is an information-theoretic
measure whose normalising term grows with the number of groups, normalised
mutual information being the usual one, so granularity is penalised rather than
rewarded. Reporting purity beside its `n` is the cheap version of the same idea.

So the guard has never fired, and could not have: with almost every cell
perfectly pure, the threshold has nothing to catch. Purity as it stands
distinguishes a cell of fifteen agreeing examples from one of fifteen
disagreeing ones - which is worth having - but not a cell of fifteen from a cell
of one, which is the distinction that matters here. Reporting purity beside its
`n`, or raising `min_examples` to three, would make the number mean what it
looks like it means. If the cell is empty it backs off to the role
family, then to the argument element, then to the declared fallback.

Measured leave-one-out over the 161 links that carry a written relation:

| level                        | accuracy          | 95% CI    | predicts on  |
| ---------------------------- | ----------------- | --------- | ------------ |
| exact role pair              | 81% (130/161)     | 74-86     | 85% of links |
| role family                  | 85%               | -         | 96%          |
| argument element             | 59%               | -         | 97%          |
| backed off through all three | **89%** (144/161) | **84-93** | 97%          |

Wilson intervals, on 161 links. The chain beats the exact pair, but the
intervals overlap, so "89 against 81" is a direction rather than a settled gap.

### Graph indices

Computed over the claim graph, following the fuzzy-cognitive-map literature
(Özesmi & Özesmi 2004):

```
density            = C / (N * (N - 1))
transmitter bias   = (out - in) / (out + in)
hierarchy index    = 12 / ((N-1) * N * (N+1)) * SUM (outdeg_i - mean_outdeg)^2
```

Transmitter bias is what supports a statement like "he argues _from_ customs
data and _about_ balance-of-payments data": customs runs 45 out against 21 in,
balance-of-payments 34 against 33.

Özesmi & Özesmi also give published comparison figures, which let the shape of
these maps be checked rather than asserted. They report cause maps averaging
**23 ± 2 variables and 37 ± 3 connections**. This corpus averages **17.9 nodes
and 22.8 links** per map (nodes 13-24, links 13-36). So the maps are comparable
in size and **sparser in connection**: 1.27 links per node against their 1.61,
and 0.96 counting only links the annotator drew. Sparser is the expected
direction - an argument map records only the links someone chose to draw,
where a cause map is elicited until the participant stops - but it is a
measured gap, not a neutral one, and it is the quantitative form of the
isolated-question problem.

The hierarchy index measures star-ness, not layeredness, so a value near zero
does not mean the maps are flat. An earlier draft of that script predicted the
opposite and was wrong.

### Agreement, and the independence of the two axes

`agreement.py` implements Krippendorff's alpha for nominal data in
coincidence-matrix form, `alpha = 1 - Do/De`, where `Do` is observed
disagreement and `De` is the disagreement expected by chance. It returns
_undefined_ rather than 1.0 when `De` is zero, which is the case a naive
implementation gets wrong. It is validated against positive and negative
controls and has nothing to measure, because no article was annotated twice.

The claim that the role axis and the subject axis carry different information is
measured rather than assumed. Over the 661 claim-term assignments on
`variable`, against the 11 role families:

```
Cramer's V = 0.20,  0.00 after Bergsma's bias correction on an 11 x 34 table
normalised mutual information = 0.08
permutation p = 0.89  (5,000 shuffles of the ROLE across claims)
```

The statistic is computed over claim-term assignments, because the subject axis
is multi-label - a claim may carry up to three variables - so n (661) exceeds
the claim count (359) and the chi-square reference distribution does not apply.

**The exchangeable unit is the claim, not the assignment**, and the null
respects that: each shuffle permutes the _role_ across claims while keeping each
claim's own set of terms intact, then recomputes the statistic over the expanded
assignment list. An earlier version of this section shuffled assignment-level
labels, which breaks the within-claim dependency and builds an easier null; the
figures below replace it.

| crossing                   | claims | assignments | V     | corrected | p         |
| -------------------------- | ------ | ----------- | ----- | --------- | --------- |
| role family x `variable`   | 359    | 661         | 0.202 | **0.000** | 0.89      |
| role family x `instrument` | 180    | 210         | 0.215 | **0.000** | 0.77      |
| role family x `data_basis` | 109    | 128         | 0.337 | **0.193** | **0.024** |

`variable` and `instrument` show no detectable association, which is what makes
the cross two questions rather than one asked twice. `data_basis` is the
exception, and correcting the unit made it **stronger**, not weaker: p moved
from 0.048 to 0.024. It still does not clear a Bonferroni threshold for three
tests (0.0167), and it points the way the transmitter-bias result already did -
evidence claims rest on customs data, discrepancy claims on balance of payments

- so it is a property of the corpus rather than a flaw in the axes. But it is
  no longer comfortably dismissible.

### What consumes each number

The formulas matter less than their consumer. Every number falls into one of
four groups, and knowing which prevents the commonest misreading - treating a
similarity score as evidence.

| number                        | what reads it                                                                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| cosine                        | **writes data**: picks which paragraph is recorded against the claim                                                                                                                                       |
| the literal test              | **writes data**: sets the grade, which decides how the export renders the line - anchored prints bold and names the shared literal, everything else prints _not a citation_ and is never shown as a source |
| purity                        | **writes data**: stored on every derived link, and carried into the interchange-format export                                                                                                              |
| margin                        | **routes a person**: bands the review queue - `clear` above 0.10, `moderate` 0.05-0.10, `tie` below 0.05, where the matcher is openly guessing and a reviewer must read both paragraphs                    |
| purity < 0.60                 | **routes a person**: raises a review item                                                                                                                                                                  |
| indices                       | **reported**: loaded by the exporter and printed on each topic page                                                                                                                                        |
| Cramér's V, MI, permutation p | **read by nothing**: a one-off check that crossing the axes asks two questions rather than one twice                                                                                                       |
| leave-one-out accuracy        | **read by nothing**: justifies the back-off chain's existence                                                                                                                                              |
| Krippendorff's alpha          | **waiting**: implemented, validated, nothing to measure                                                                                                                                                    |

Current state of the queue the margin feeds: **0 of 270 candidates reviewed**;
140 `clear`, 46 `moderate`, 84 `tie`. Passage provenance therefore stands at 69
anchored plus 0 hand-confirmed, out of 359 claims.

The rule underneath all of it: **no score is ever promoted into evidence.** A
cosine of 0.9 with no shared literal is still rendered as not a citation. The
arithmetic ranks, flags and describes; it never asserts.

### Where more arithmetic would not help

Not in the passage matcher. Its ceiling is human review of the 270 candidates,
not a better similarity. The two openings are the **roll-up** - parent terms are
declared for 53 of 77 and nothing queries them, which would take two-facet
coverage from 21% to 87% of bindings - and **`ask.py`**, which is still flat
tf-idf and reads neither axis nor the graph indices.

---

## Running it

```
python scripts/parse_maps.py                    # maps -> claims, links
python scripts/label_facets.py                  # subject axis
python scripts/label_facets.py --inherit-where  # the two repairs
python scripts/graph_indices.py                 # signs and indices
python scripts/link_passages.py                 # claim -> paragraph
python scripts/export_canvas.py                 # one canvas per article
python scripts/export_obsidian.py               # the vault, and index.md
```

`export_canvas.py` runs **before** `export_obsidian.py` on purpose: the graph
statistics written into `index.md` count the vault as it stands when the export
runs, so building the canvases afterwards leaves that line reporting one note
and one link fewer than the vault holds. Everything else in the sequence is
order-independent, and the whole chain was verified against a clean rebuild on
2026-10-23: wiping every generated file and running it again reproduces
`data/` and the vault with no content differences.

Checks worth running after a change:

```
python scripts/label_facets.py --report   # term distribution, saturation
python scripts/label_facets.py --eval     # 30/34 fixtures, 88% (CI 73-95)
python scripts/trace.py --audit           # provenance coverage, link by link
python scripts/export_aif.py --check      # interchange-format conformance
```

The vault's query blocks in `Cells.md` need the **Dataview** plugin, which is
not committed - install it from Settings > Community plugins, then reload
(`Ctrl+R`). Without it those blocks render as plain text; nothing else changes.

`label_facets.py` needs the `anthropic` SDK and an API key; everything else is
standard library plus PyYAML. `--import-json` ingests the same payload the API
would return, through the same validation, if you have no key.

---

## Known limits

- **Nothing has been double-annotated.** Three annotators split the corpus, but
  the split is disjoint: no article has two independent annotations, so the
  agreement harness (`agreement.py`) - Krippendorff's alpha, the standard
  instrument for argument annotation (Stab & Gurevych 2017; Habernal & Gurevych
  1.  - still has nothing to measure.
- **The recovered links may be layout, not argument.** Measured over the maps:
  all 20 corpus maps use `~~~`, and in all 20 every such line sits after the
  last arrow, in a trailing block;
  **0 of 111** recovered pairs also have a drawn arrow; and in the 14 maps where
  `~~~` leaves the question node, that question has **no drawn edge at all**.
  Writing the argument in arrows and then adding a block of `~~~` to position
  boxes is the ordinary use of that operator.

  But the usage tracks the **template, not the person**. Three annotators split
  this corpus, and the per-map counts are near-constant within each template
  family: `banner` 8.0 lines per map and **0** claim-to-claim, `meta` exactly
  3.0, `plain` 4.4. Every claim-to-claim link comes from `plain` (86) and `meta`
  (25); the `banner` maps use `~~~` only to chain containers. Three people
  producing the same per-map count means the convention was inherited from the
  template rather than invented at the desk.

  So the question is not "did someone slip" but "what does the template's
  convention mean" - and whoever wrote the templates can answer it. Until then
  the endpoint test is mechanical while the _interpretation_ is a judgement, and
  the fallback relation signs **0** so no support count moves either way.

- **The purity guard has never fired.** `flag_below_purity` is 0.60 and no
  role-pair cell falls below it, because 44 of the 49 cells with any evidence
  are perfectly pure - 24 of them resting on a single example, where purity is
  1.00 by construction. The threshold catches disagreement, which this corpus
  does not have, and not thinness, which it has a lot of.
- **108 of 111 recovered relations are convention, not evidence.** Even granting
  the interpretation above, they carry a declared fallback because nothing in the
  corpus evidences anything better.
- **An annotation scheme may not travel.** Daxenberger et al. (2017) compared
  claim annotation across six datasets and found the divergent conceptualisation
  of a "claim" between them actively harmful to cross-domain classification,
  with shared lexical properties and system configuration the only things that
  partly bridged it. The role vocabulary here is this team's conceptualisation
  of a claim, so their result is the direct warning against assuming it carries
  to another annotator or another thinker.
- **The labels in `data/` were not produced by a pipeline run.** Every one of
  the 1,450 rows in `data/node_facets.csv` carries
  `model: claude-opus-5 (in-session)`: they were produced by a model inside a
  working session and ingested through `label_facets.py --import-json`, which
  applies the same schema, caps, repairs and provenance columns as a live run.
  What that means precisely: the validation is real, the labels are real, and
  the **run is not reproducible**. There is no request id, no timestamp, no
  temperature and no sampling seed, and `label_facets.py` sets none when it
  calls the API, so re-running it would produce a different labelling and
  nothing here would say by how much. Every figure in this document that rests
  on the subject axis - the 41% baseline, the fixture score, the independence
  test - inherits that. The fix is a single clean run with the model version,
  parameters and a run id written to each row; until then, treat the subject
  axis as one careful pass rather than a measured process.
- **The vocabulary saw the corpus.** All 77 terms were drafted while reading
  these 20 articles, so the fixture score measures internal consistency rather
  than accuracy. A held-out article is the test that has not been run. The
  fixture set is also ours rather than a standard benchmark, which is the
  general condition of this area: reviewing 36 papers on LLMs in ontology
  engineering, Li, Garijo & Poveda-Villalón (2026) report a lack of
  homogenisation in task definitions, datasets and evaluation. That excuses
  nothing, but it says the comparison class does not exist yet.
- **Two facets were minted without a reuse search.** `variable`, `country` and
  `bloc` align every term to a published code; `instrument` and `data_basis`
  align none of their 24, which carry 23% of all labels. See `scripts/README.md`
  under "Scaling up later".
- **Almost nothing crosses articles.** The concept layer covers 9 of 359 claims.
  Everything else that looks like a cross-article link is co-occurrence.
- **Claims have a date but no period.** Each claim carries its article's
  publication date and no sense of the span it is _about_, across a corpus
  running 2017 to 2026. The bi-temporal edges in Rasmussen et al. (2025) are
  the obvious model: an assertion valid over one interval, recorded at another.
  Nothing here implements that, and "what did he think in 2019" is currently
  answerable only by publication date.
- ~~The anchored-passage count disagrees between sources.~~ **Traced and not a
  defect**: `data/node_passages.csv` keeps up to three paragraphs for an
  anchored claim, and 17 claims have more than one, so 92 rows cover 69 distinct
  claims. The vault writes one line per claim. Both numbers are right; quote 69
  when counting claims and 92 only when counting rows.

---

## References

Alphabetical. Every entry checked against the publication, its publisher's
record or its arXiv listing on 2026-10-23.

- **Ash, E., Gauthier, G. & Widmer, P. (2024).** Relatio: Text Semantics Capture Political and Economic Narratives. *Political Analysis* 32(1), 115-132. Cambridge University Press.
  *Used here for:* read, not used: narrative extraction without a controlled vocabulary.

- **Axelrod, R. (ed.) (1976).** *Structure of Decision: The Cognitive Maps of Political Elites*. Princeton University Press.
  *Used here for:* a sign on each edge, and no weight.

- **Babaei Giglou, H., D'Souza, J. & Auer, S. (2023).** LLMs4OL: Large Language Models for Ontology Learning. *The Semantic Web - ISWC 2023*, LNCS 14265, 408-427. Springer.
  *Used here for:* typing terms against a fixed vocabulary rather than inducing one.

- **Chesñevar, C., McGinnis, J., Modgil, S., Rahwan, I., Reed, C., Simari, G., South, M., Vreeswijk, G. & Willmott, S. (2006).** Towards an argument interchange format. *The Knowledge Engineering Review* 21(4), 293-316. doi:10.1017/S0269888906001044.
  *Used here for:* claims as information nodes, separate from reasoning-step nodes.

- **Daxenberger, J., Eger, S., Habernal, I., Stab, C. & Gurevych, I. (2017).** What is the Essence of a Claim? Cross-Domain Claim Identification. *EMNLP 2017*, 2055-2066. arXiv:1704.07203.
  *Used here for:* a conceptualisation of "claim" does not transfer cleanly between domains.

- **Groth, P., Gibson, A. & Velterop, J. (2010).** The anatomy of a nanopublication. *Information Services & Use* 30(1-2), 51-56.
  *Used here for:* one assertion published together with its provenance.

- **Grüninger, M. & Fox, M. S. (1995).** Methodology for the Design and Evaluation of Ontologies. *Workshop on Basic Ontological Issues in Knowledge Sharing*, IJCAI-95, Montreal.
  *Used here for:* competency questions as the bound on a vocabulary.

- **Habernal, I. & Gurevych, I. (2017).** Argumentation Mining in User-Generated Web Discourse. *Computational Linguistics* 43(1), 125-179. arXiv:1601.02403.
  *Used here for:* agreement measurement, including unitizing.

- **Han, X., Yu, P., Liu, Z., Sun, M. & Li, P. (2018).** Hierarchical Relation Extraction with Coarse-to-Fine Grained Attention. *EMNLP 2018*, 2236-2245.
  *Used here for:* a hierarchy over relations is the standard handle on long-tail relations.

- **Heddaya, M., Zeng, Q., Tan, C., Voigt, R. & Zentefis, A. (2024).** Causal Micro-Narratives. *Proceedings of the 6th Workshop on Narrative Understanding (WNU)*, 67-84. ACL. arXiv:2410.05252.
  *Used here for:* one label for an author's many phrasings of the same thing.

- **Hernández, D., Hogan, A. & Krötzsch, M. (2015).** Reifying RDF: What Works Well With Wikidata? *11th International Workshop on Scalable Semantic Web Knowledge Base Systems (SSWS)*, CEUR-WS 1457, 32-47.
  *Used here for:* how provenance attaches to a single claim.

- **Kosko, B. (1986).** Fuzzy cognitive maps. *International Journal of Man-Machine Studies* 24(1), 65-75.
  *Used here for:* the weighted formulation, declined: strength of support is never stated.

- **Laukkanen, M. (1994).** Comparative Cause Mapping of Organizational Cognitions. *Organization Science* 5(3), 322-343. doi:10.1287/orsc.5.3.322.
  *Used here for:* what to control so two annotators' maps can be compared.

- **Li, J., Garijo, D. & Poveda-Villalón, M. (2026).** Large Language Models for Ontology Engineering: A Systematic Literature Review. *Semantic Web Journal*. doi:10.1177/22104968261465514.
  *Used here for:* no homogenisation in task definitions, datasets or evaluation across this area.

- **Manning, C. D., Raghavan, P. & Schütze, H. (2008).** *Introduction to Information Retrieval*, ch. 16 §16.3 "Evaluation of clustering". Cambridge University Press.
  *Used here for:* the purity measure, and its singleton pathology.

- **Markóczy, L. & Goldberg, J. (1995).** A method for eliciting and comparing causal maps. *Journal of Management* 21(2), 305-333.
  *Used here for:* a node vocabulary fixed before anyone draws.

- **Nasir, F. et al. (2026).** OntoKG-EQ: A provenance-grounded, competency-question-governed knowledge graph for auditable analyst querying. arXiv:2609.08869.
  *Used here for:* question governance paired with per-claim provenance; governs with five fixed questions.

- **Özesmi, U. & Özesmi, S. L. (2004).** Ecological models based on people's knowledge: a multi-step fuzzy cognitive mapping approach. *Ecological Modelling* 176(1-2), 43-64.
  *Used here for:* density, centrality, transmitter bias, hierarchy index, and the published map-size comparison.

- **Poveda-Villalón, M., Fernández-Izquierdo, A., Fernández-López, M. & García-Castro, R. (2022).** LOT: An industrial oriented ontology engineering framework. *Engineering Applications of Artificial Intelligence* 111, 104755. doi:10.1016/j.engappai.2022.104755.
  *Used here for:* reuse a published term before minting a new one.

- **Ranganathan, S. R. (1933).** *Colon Classification*. Madras Library Association.
  *Used here for:* a subject described across several independent axes combined, not one place in one tree.

- **Rasmussen, P., Paliychuk, P., Beauvais, T., Ryan, J. & Chalef, D. (2025).** Zep: A Temporal Knowledge Graph Architecture for Agent Memory. arXiv:2501.13956.
  *Used here for:* read, not used: bi-temporal edges, the model for the missing period dimension.

- **Stab, C. & Gurevych, I. (2017).** Parsing Argumentation Structures in Persuasive Essays. *Computational Linguistics* 43(3), 619-659. arXiv:1604.07370.
  *Used here for:* agreement measurement for argument annotation.

- **Toulmin, S. E. (1958).** *The Uses of Argument*. Cambridge University Press. Summarised by the [Purdue OWL](https://owl.purdue.edu/owl/general_writing/academic_writing/historical_perspectives_on_argumentation/toulmin_argument.html), which sets out all six elements.
  *Used here for:* the six argument elements, as the drawing's stages and the top of the role hierarchy.

- **W3C (2013).** PROV-O: The PROV Ontology. W3C Recommendation, 30 April 2013. Eds. T. Lebo, S. Sahoo & D. McGuinness. <https://www.w3.org/TR/prov-o/>
  *Used here for:* provenance predicates for assertions a process derived rather than a person asserted.

**Read and not used**, recorded so the choice is visible: Ash, Gauthier &
Widmer (Relatio) and Rasmussen et al. (Zep) above, plus Noy, N. F. &
McGuinness, D. L. (2001), *Ontology Development 101: A Guide to Creating Your
First Ontology*, Stanford KSL Technical Report KSL-01-05, and Walton &
Macagno on argumentation-scheme classification.

**Two notes on what the sources do and do not say.** Daxenberger et al. was
previously cited here for "coarse decisions transfer across corpora while
fine-grained ones do not", which is not its finding: across six datasets it
reports that the divergent conceptualisation of a claim between domains is
harmful to cross-domain classification, with shared lexical properties and
system configuration partly bridging it. It now appears under Limits, where
that result applies. And Han et al. is borrowed for its premise rather than its
method: their coarse-to-fine attention over a relation hierarchy is a neural
model, while the back-off here is a majority vote with no attention and no
model.

The job of mapping an author's many phrasings onto one label is cited to
Heddaya et al. rather than to Relatio, because Heddaya classifies against an
expert-built ontology fixed in advance, which is what `label_facets.py` does;
Relatio discovers its labels by clustering phrase variants with no controlled
vocabulary.
