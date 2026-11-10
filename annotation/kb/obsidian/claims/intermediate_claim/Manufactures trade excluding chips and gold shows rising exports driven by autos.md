---
type: intermediate_claim
level: L4
date: 2026-07-27
article: "Is China’s Surplus Really Shrinking?"
doc: setser_2026-07-27_is-chinas-surplus-really-shrinking
node_id: C2
family: llm
aliases: ["Manufactures trade excluding chips and gold shows rising exports driven by autos, with flat imports, so the manufacturing surplus keeps rising"]
relation_sources: [llm]
variable: [manufacturing-trade-balance, export-volumes]
country_subject: [china]
data_basis: [customs]
tags: [type/intermediate_claim, level/L4, family/llm, variable/manufacturing-trade-balance, variable/export-volumes, country/china, where/china, data_basis/customs]
---

# Manufactures trade excluding chips and gold shows rising exports driven by autos, with flat imports, so the manufacturing surplus keeps rising.

## Leads to
- **+1 supports** → [[China's underlying surplus is still rising; it continues to rely heavily on exports]] `main_claim`

## Rests on
- [[Higher chip prices raise both chip imports and exports, so they barely move the net]] `mechanism` **+1 supports** this
- [[Refined gold is classified as a manufacture, so gold flows contaminate the manufacturing]] `stated_assumption` **+1 supports** this

## Subject

- **variable**: [[manufacturing-trade-balance]], [[export-volumes]]
- **country**: [[china]]
- **data_basis**: [[customs]]

## Source
- Article: [[2026-07-27 Is China’s Surplus Really Shrinking]]
- Mapped by the model: `annotation/articles/setser_2026-07-27_is-chinas-surplus-really-shrinking/claude-opus-5.5/annotation.json`
- Passage: **p12** — _cited by the model, `abstracts`; unreviewed_
- Passage: **p13** — _cited by the model, `states`, excerpt checked word for word; unreviewed_
- Passage: **p21** — _cited by the model, `abstracts`; unreviewed_
- Passage: **p27** — _cited by the model, `abstracts`; unreviewed_
- Published: https://www.cfr.org/articles/is-chinas-surplus-really-shrinking
- Node `setser_2026-07-27_is-chinas-surplus-really-shrinking#C2` · level L4 · type resolved by `llm`
- Full chain: `python scripts/trace.py setser_2026-07-27_is-chinas-surplus-really-shrinking#C2`
