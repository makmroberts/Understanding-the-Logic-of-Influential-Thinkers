# Codebook

Rules for filling the architecture, so two people reading the same article
produce the same map. Statuses follow the skill: `filled`, `implicit`,
`absent`, `na`.

## How to annotate

1. Read the article once without annotating.
2. Fill Level 5 first — find the main claim — then work backwards.
3. Give every slot a status (`implicit`, `absent` or `na` when it has no
   stated content). Never leave a bare blank.
4. Draw only the edges the article actually makes, using only the legal types.

## Slot definitions

### Level 0 · Question & framing

| Slot | Definition | Boundary |
|---|---|---|
| **Question** | The problem the article sets out to answer, in one sentence. Required. | Not the title. If the article never poses one, infer it and mark it `implicit`. |
| **Anomaly** | A specific prediction that failed, used as the starting point. | Only when a named forecast is shown to be wrong. General surprise is not an anomaly. |
| **Position map** | Named actors and what each claimed, before the author weighs in. | Needs at least two identified positions. One opposing view belongs in Level 6. |

### Level 1 · Priors & assumptions

| Slot | Definition | Boundary |
|---|---|---|
| **Stated assumption** | Something the author openly takes as given. Required. | If he argues for it, it is evidence or a claim, not a prior. |
| **Hidden assumption** | Needed for the argument to work, never stated. Required. | Test: remove it and does a step collapse? If not, it is not load-bearing. |
| **Revised prior** | A belief the author states **and marks as wrong**. | Must be first-person and explicit — "I was surprised", "I thought", "contrary to a forecast I made". Someone *else* being wrong is a Position or an Opposing view. |
| **Accounting identity** | A balance that must hold by definition, doing work in the argument. | Only when stated. An identity used silently is a Hidden assumption. |
| **Source credibility** | A prior about whoever produced the data, not about the economics. | Doubting a *number* is evidence. Doubting the *producer* is this slot. |

### Level 1b · Frame & scope

| Slot | Definition | Boundary |
|---|---|---|
| **Benchmark** | An external target the evidence is measured against, set by someone else. | Must be external and specific. The author's own expectation is a prior. |
| **Scope choice** | A definitional decision that changes the verdict. | Only when the choice is stated and consequential — which categories, which baseline, what is excluded. |

### Level 2 · Evidence

| Slot | Definition | Boundary |
|---|---|---|
| **Data** | Numbers and charts cited in support. Required. | A number that is a *consequence* of the mechanism belongs with the claim or the reconstruction, not here. |
| **Studies & sources** | Research or named experts cited. Required. | Self-citation currently lands here. A dedicated slot is proposed. |
| **Rival measurement** | A second series measuring the same quantity. | Needs two series of the *same* thing. Two different indicators are just Data. |
| **Discrepancy** | The gap between rival measurements, treated as the finding itself. | Requires Rival measurement to be filled. |

### Level 3 · Mechanisms

| Slot | Definition | Boundary |
|---|---|---|
| **Mechanism A / B** | A causal channel: how one thing produces another. Tag `kind:`. | `economic` = a channel in the world. `distortion` = how a statistic gets misstated. Do not mix kinds in one node. |

### Level 4 · Intermediate claims

| Slot | Definition | Boundary |
|---|---|---|
| **Intermediate claim** | What the mechanisms add up to, short of the conclusion. Required. | |
| **Case type** | A branch, where the argument sorts cases rather than converging. | Needs at least two types with *different* consequences. Scoring categories in sequence is not sorting. |
| **Policy reductio** | Taking someone's proposal and running it to a consequence they would reject. | Must be a proposal the author did not make. Criticising an argument is just an Opposing view. |

### Level 5 · Conclusion

| Slot | Definition | Boundary |
|---|---|---|
| **Main claim** | The conclusion. Required. Tag `type:`. | `single` one claim · `enumerated` several parallel · `typology` the classification is the answer · `unresolved` explicitly declines to choose. |
| **Reconstruction** | A replacement quantity built after showing the official one is wrong. | Requires a rejected measure. An estimate with no rejected counterpart is Data. |
| **Recommendation** | A normative "should", separate from the claim. | Must be addressed to someone. "This matters" is not a recommendation. |

### Level 6 · Counterpoints

| Slot | Definition | Boundary |
|---|---|---|
| **Opposing view** | The position argued against. Required. | May appear anywhere in the text, including the opening. |
| **Caveat** | Where the author concedes the claim may not hold. Required. | Must be the author's own concession. |
| **Other explanation** | A rival cause the author admits but does not adopt. | If he picks one, it is a Mechanism. |
| **Deferred question** | Explicitly postponed. | Needs explicit postponement — "for a future post", "too early to tell". |

## Legal edge types

An article may use only these. If a relation does not fit one, the slot
assignment is probably wrong.

| Type | Meaning | Style |
|---|---|---|
| `supports` | A gives reason to accept B | solid |
| `licenses` | Without A, the step to B is invalid | solid |
| `bounds` / `compared against` | A constrains how B is measured | solid |
| `motivates` | A is the reason B is proposed | solid |
| `revises` | A is a prior the author now rejects | dashed |
| `reconstructs` | A replaces a quantity shown to be wrong | solid |
| `rebuts` | A argues directly against B | dashed |
| `qualified by` | B limits where A holds | dashed |
| `undercut by` | B weakens A without refuting it | dashed |
| `defers` | A sets B aside explicitly | dashed |

## Three rules on edges

1. **Legal type** — only the ten above.
2. **Forward only** — an edge runs to the same level or a later one. If you
   need a backward edge, the slot assignment is wrong.
3. **Both ends filled** — never draw an edge into or out of an empty slot.

`pva.py validate` checks all three.

**Direction matters.** Evidence points *to* what it supports. A figure that
measures the *result* of a mechanism is not evidence for that mechanism — it
belongs downstream.

**The architecture does not fix node-to-node arrows.** It says which levels may
connect and how. Within those rules the annotator draws what the article
actually argues. The only exceptions are definitional: a revised prior revises a
prior, a scope choice bounds a benchmark, a discrepancy comes from a rival
measurement, a reconstruction comes from a main claim.

## Empty states

| State | Meaning | Counted |
|---|---|---|
| `implicit` | Present, never stated outright | separately |
| `absent` | The genre allows it, this author did not | empty |
| `na` | Category error for this kind of article | empty |

## Known gaps

- **Self-citation** has no slot; it goes in Studies & sources.
- **Prediction** has no slot. Some articles make checkable forward claims that
  could later be scored right or wrong.
