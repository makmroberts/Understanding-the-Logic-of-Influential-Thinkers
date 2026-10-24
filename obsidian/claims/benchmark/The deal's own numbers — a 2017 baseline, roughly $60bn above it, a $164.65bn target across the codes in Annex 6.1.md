---
type: benchmark
level: L1B
date: 2020-07-08
article: "Slouching Toward Phase One"
doc: setser_jul_8_20
node_id: BM
family: banner
relation_sources: [label]
variable: [bilateral-trade-flows, import-volumes]
country_subject: [china]
country_counterpart: [us]
instrument: [purchase-commitments]
data_basis: [customs]
bilateral: true
tags: [type/benchmark, level/L1B, family/banner, variable/bilateral-trade-flows, variable/import-volumes, country/china, where/china, country/us, where/us, instrument/purchase-commitments, data_basis/customs, shape/bilateral]
---

# The deal's own numbers — a 2017 baseline, roughly $60bn above it, a $164.65bn target across the codes in Annex 6.1

## Leads to
- **+1 bounds** → [[First-half pace implies ~$83bn, below the 2017 baseline of ~$101bn and even below 2019; energy at 7% of its target; 1m]] `evidence_data` _(drawn as "compared against")_
- **+1 licenses** → [[Category by category manufacturing will not close the gap, agriculture is behind but Q4 is still live, energy]] `intermediate_claim`

## Rests on
- [[Services excluded because in-China sales are not exports; aircraft adjusted out; only the listed HS codes counted]] `scope_choice` **+1 bounds** this

## Subject

- **variable**: [[bilateral-trade-flows]], [[import-volumes]]
- **country**: [[us]] _(counterpart)_, [[china]]
- **instrument**: [[purchase-commitments]]
- **data_basis**: [[customs]]

## Source
- Article: [[2020-07-08 Slouching Toward Phase One]]
- Authored map: `mermaid_code/setser_jul_8_20.mmd`
- Passage: **p7** — **states**, anchored on `60billion`, a literal the claim and the paragraph share
- Passage: **p8** — **states**, anchored on `164.65billion 6.1`, a literal the claim and the paragraph share
- Published: https://www.cfr.org/articles/slouching-toward-phase-one
- Node `setser_jul_8_20#BM` · level L1B · type resolved by `header`
- Full chain: `python scripts/trace.py setser_jul_8_20#BM`
