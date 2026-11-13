---
type: reconstruction
level: L5
date: 2026-07-27
article: "Is China’s Surplus Really Shrinking?"
doc: setser_2026-07-27_is-chinas-surplus-really-shrinking
node_id: RC
family: llm
aliases: ["Excluding gold, the goods surplus rose over $80 billion in H1 2026 and would be near 7% of GDP in Q2"]
relation_sources: [llm]
variable: [goods-trade-balance]
country_subject: [china]
data_basis: [customs]
tags: [type/reconstruction, level/L5, family/llm, variable/goods-trade-balance, country/china, where/china, data_basis/customs]
---

# Excluding gold, the goods surplus rose over $80 billion in H1 2026 and would be near 7% of GDP in Q2.

## Leads to
- **+1 supports** → [[China's underlying surplus is still rising; it continues to rely heavily on exports]] `main_claim`

## Rests on
- [[Gold imports reached $146 billion in H1 2026, nearly $100 billion above H1 2025, and 1.5%]] `evidence_data` **+1 supports** this
- [[Gold imports should be netted out of the headline balance because they are a one-off]] `scope_choice` **+1 licenses** this
- [[Oil price gains are offset by collapsing import volumes, so the commodity bill rose]] `intermediate_claim` **+1 supports** this
- [[Higher chip prices raise both chip imports and exports, so they barely move the net]] `mechanism` **+1 supports** this

## Subject

- **variable**: [[goods-trade-balance]]
- **country**: [[china]]
- **data_basis**: [[customs]]

## Source
- Article: [[2026-07-27 Is China’s Surplus Really Shrinking]]
- Mapped by the model: `annotation/articles/setser_2026-07-27_is-chinas-surplus-really-shrinking/claude-opus-5.5/annotation.json`
- Passage: **p7** — _cited by the model, `states`, excerpt checked word for word; unreviewed_
- Passage: **p16** — _cited by the model, `abstracts`; unreviewed_
- Passage: **p22** — _cited by the model, `abstracts`; unreviewed_
- Published: https://www.cfr.org/articles/is-chinas-surplus-really-shrinking
- Node `setser_2026-07-27_is-chinas-surplus-really-shrinking#RC` · level L5 · type resolved by `llm`
- Full chain: `python scripts/trace.py setser_2026-07-27_is-chinas-surplus-really-shrinking#RC`
