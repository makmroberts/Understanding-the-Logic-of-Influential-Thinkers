---
type: evidence_data
level: L2
date: 2026-07-27
article: "Is China’s Surplus Really Shrinking?"
doc: setser_2026-07-27_is-chinas-surplus-really-shrinking
node_id: E2
family: llm
aliases: ["Gold imports reached $146 billion in H1 2026, nearly $100 billion above H1 2025, and 1.5% of GDP in Q2, even as gold prices fell"]
relation_sources: [llm]
variable: [import-volumes, commodity-prices]
country_subject: [china]
data_basis: [customs]
tags: [type/evidence_data, level/L2, family/llm, variable/import-volumes, variable/commodity-prices, country/china, where/china, data_basis/customs]
---

# Gold imports reached $146 billion in H1 2026, nearly $100 billion above H1 2025, and 1.5% of GDP in Q2, even as gold prices fell.

## Leads to
- **+1 supports** → [[Excluding gold, the goods surplus rose over $80 billion in H1 2026 and would be near 7%]] `reconstruction`

## Rests on
- [[Gold imports should be netted out of the headline balance because they are a one-off]] `scope_choice` **+1 bounds** this
- [[Refined gold is classified as a manufacture, so gold flows contaminate the manufacturing]] `stated_assumption` **0 frames** this

## Subject

- **variable**: [[import-volumes]], [[commodity-prices]]
- **country**: [[china]]
- **data_basis**: [[customs]]

## Source
- Article: [[2026-07-27 Is China’s Surplus Really Shrinking]]
- Mapped by the model: `annotation/articles/setser_2026-07-27_is-chinas-surplus-really-shrinking/claude-opus-5.5/annotation.json`
- Passage: **p6** — _cited by the model, `states`, excerpt checked word for word; unreviewed_
- Passage: **p9** — _cited by the model, `abstracts`; unreviewed_
- Published: https://www.cfr.org/articles/is-chinas-surplus-really-shrinking
- Node `setser_2026-07-27_is-chinas-surplus-really-shrinking#E2` · level L2 · type resolved by `llm`
- Full chain: `python scripts/trace.py setser_2026-07-27_is-chinas-surplus-really-shrinking#E2`
