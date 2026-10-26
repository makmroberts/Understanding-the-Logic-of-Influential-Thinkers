---
type: evidence_data
level: L2
date: 2020-02-26
article: "Do tariffs change the trade balance, and who absorbed the Q4 US demand drop?"
doc: setser_feb_26_20
node_id: D5
family: plain
relation_sources: [arrow, layout_operator]
variable: [bilateral-trade-flows, import-volumes]
country_subject: [us]
bloc_counterpart: [southeast-asia]
data_basis: [customs]
bilateral: true
tags: [type/evidence_data, level/L2, family/plain, variable/bilateral-trade-flows, variable/import-volumes, country/us, where/us, bloc/southeast-asia, where/southeast-asia, data_basis/customs, shape/bilateral]
---

# Vietnam exports to US +$17.5B

> Far short of the fall in China imports

## Leads to
- **+1 supports** → [[Diversion no longer offsets China]] `intermediate_claim`
- **+1 supports** → [[Lower capex → lower imports]] `mechanism`

## Rests on
- [[Trade balance = saving − investment]] `hidden_assumption` **0 frames** this

## Subject

- **variable**: [[bilateral-trade-flows]], [[import-volumes]]
- **country**: [[us]]
- **bloc**: [[southeast-asia]] _(counterpart)_
- **data_basis**: [[customs]]

## Source
- Article: [[2020-02-26 Do tariffs change the trade balance, and who absorbed the Q4 US demand drop]]
- Authored map: `mermaid_code/setser_feb_26_20.mmd`
- Passage: **p10** — **states**, anchored on `17.5billion`, a literal the claim and the paragraph share
- Published: https://www.cfr.org/articles/us-shock-global-demand-q4-coronavirus
- Node `setser_feb_26_20#D5` · level L2 · type resolved by `class`
- Full chain: `python scripts/trace.py setser_feb_26_20#D5`
