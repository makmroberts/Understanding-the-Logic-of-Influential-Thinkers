---
type: intermediate_claim
level: L4
date: 2020-02-26
article: "Do tariffs change the trade balance, and who absorbed the Q4 US demand drop?"
doc: setser_feb_26_20
node_id: C2
family: plain
relation_sources: [arrow]
variable: [bilateral-trade-flows, import-volumes]
country_subject: [us]
country_counterpart: [china]
instrument: [tariffs]
bilateral: true
tags: [type/intermediate_claim, level/L4, family/plain, variable/bilateral-trade-flows, variable/import-volumes, country/us, where/us, country/china, where/china, instrument/tariffs, shape/bilateral]
---

# Diversion no longer offsets China

> Imports from other countries stopped making up the gap

## Leads to
- **+1 supports** → [[Main claim the US demand shock was exported]] `main_claim`

## Rests on
- [[Q4 imports weak]] `evidence_data` **+1 supports** this
- [[Vietnam exports to US +$17.5B]] `evidence_data` **+1 supports** this

## Subject

- **variable**: [[bilateral-trade-flows]], [[import-volumes]]
- **country**: [[china]] _(counterpart)_, [[us]]
- **instrument**: [[tariffs]]

## Source
- Article: [[2020-02-26 Do tariffs change the trade balance, and who absorbed the Q4 US demand drop]]
- Authored map: `mermaid_code/setser_feb_26_20.mmd`
- Passage: p11 — _proposed `abstracts`, score 0.350; unreviewed, not a citation_
- Published: https://www.cfr.org/articles/us-shock-global-demand-q4-coronavirus
- Node `setser_feb_26_20#C2` · level L4 · type resolved by `class`
- Full chain: `python scripts/trace.py setser_feb_26_20#C2`
