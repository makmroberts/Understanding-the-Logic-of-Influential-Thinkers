---
type: reconstruction
level: L5
date: 2024-08-14
article: "China's Imaginary Trade Data"
doc: setser_aug_14_24
node_id: RC
family: banner
aliases: ["Goods surplus understated by ~$300bn, over 1.5pp of GDP; true current account surplus close to $700bn — use the customs data"]
relation_sources: [label]
variable: [current-account, goods-trade-balance]
country_subject: [china]
data_basis: [balance-of-payments, customs]
tags: [type/reconstruction, level/L5, family/banner, variable/current-account, variable/goods-trade-balance, country/china, where/china, data_basis/balance-of-payments, data_basis/customs]
---

# Goods surplus understated by ~$300bn, over 1.5pp of GDP; true current account surplus close to $700bn — use the customs data

## Leads to
- **-1 qualified by** → [[The income line carries no detail, so this cannot be checked from outside]] `caveat`

## Rests on
- [[The reported surplus is an artifact of a methodology change]] `main_claim` **+1 reconstructs** this
- [[Customs data is ground truth — never argued for, the whole case rests on it]] `hidden_assumption` **+1 licenses** this

## Subject

- **variable**: [[current-account]], [[goods-trade-balance]]
- **country**: [[china]]
- **data_basis**: [[balance-of-payments]], [[customs]]

## Source
- Article: [[2024-08-14 China's Imaginary Trade Data]]
- Authored map: `mermaid_code/setser_aug_14_24.mmd`
- Passage: **p29** — **states**, anchored on `300billion 700billion`, a literal the claim and the paragraph share
- Published: https://www.cfr.org/articles/chinas-imaginary-trade-data
- Node `setser_aug_14_24#RC` · level L5 · type resolved by `header`
- Full chain: `python scripts/trace.py setser_aug_14_24#RC`
