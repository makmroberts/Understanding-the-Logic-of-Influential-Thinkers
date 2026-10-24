# Understanding the Logic of Influential Thinkers

A queryable graph of how one analyst argues, built from his own published work.

Twenty articles by Brad Setser (CFR, *Follow the Money*) are drawn by hand as
argument maps, then parsed into **359 claims, 455 links and 1,454 subject
labels** over a closed vocabulary of 77 terms. Setser is the first analyst
through the method; it is built to take another.

## What it answers

> *What does he assume, without defending, about China?*

Seven claims, from seven different articles. No map tags that anywhere — the
answer is the intersection of two labels assigned for unrelated reasons.

Every claim is filed on two axes. **Role** is what it does in an argument: an
unstated assumption, a mechanism, a concession, a rival explanation. **Subject**
is what it is about: the variable, the economy, the policy instrument, the
evidence base. Neither is a sub-category of the other, so crossing them asks
questions neither axis can be asked alone — and the independence is measured,
not assumed (Cramér's V of 0.00 after bias correction, permutation p = 0.89).

Eleven such questions are kept as standing shapes with slots, and the vocabulary
exists only where one of them needs a term to separate two answers.

## Where to start

| | |
|---|---|
| **PROCESS.md** | How the graph is built: the steps, the reasoning behind each with its sources, how to read a claim note, what the arithmetic computes, and the limits. |
| `scripts/README.md` | The lab notebook: what was tried, what was measured, what failed. |
| `obsidian/` | The graph. Open the folder as an Obsidian vault; `index.md` is the way in, `Cells.md` holds a query per role-and-subject cell. |
| `mermaid_code/` | The twenty argument maps. These are the record; code never rewrites them. |

## Traceability

Every line records how it was known — read from the map, set by a declared rule,
or assigned by a model — so a reader can filter on provenance rather than trust
it. A claim is cited as `doc#node_id@map_rev`, because the node id alone is a
slot address that all twenty maps share.

Paragraph links are graded. `anchored` means the claim and the paragraph share a
distinctive literal, which is provenance; `candidate` means semantic overlap
only, and the vault never renders one as a source. Of 359 claims, 69 reach an
anchor.

## Running it

```
python scripts/parse_maps.py                    # maps -> claims, links
python scripts/label_facets.py                  # the subject axis
python scripts/graph_indices.py                 # signs and indices
python scripts/link_passages.py                 # claim -> paragraph
python scripts/export_canvas.py                 # one canvas per article
python scripts/export_obsidian.py               # the vault
```

Python standard library plus PyYAML; only `label_facets.py` needs the
`anthropic` SDK, and it has an offline path. Quit Obsidian before the export.
Wiping every generated file and running the chain again reproduces `data/` and
the vault with no content differences. `PROCESS.md` has the checks worth running
after a change.

## Limits

Three annotators split the twenty articles with no overlap, so no article has
two independent annotations and the agreement harness has nothing to measure.
The subject labels in `data/` came from a model session rather than a clean API
run, and every row says so. The vocabulary was written while reading these same
twenty articles, so its fixture score measures internal consistency. Of the 455
links, 294 carry no label in the source and take a declared convention. One map
is model-authored and flagged for human review. These are set out in full under
Limits in `PROCESS.md`.
