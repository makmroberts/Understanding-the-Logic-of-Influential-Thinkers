---
type: intermediate_claim
level: L4
date: 2020-02-26
article: "Do tariffs change the trade balance, and who absorbed the Q4 US demand drop?"
doc: setser_feb_26_20
node_id: C1
family: plain
relation_sources: [arrow, label]
variable: [gdp-growth, goods-trade-balance]
country_subject: [us]
instrument: [tariffs]
tags: [type/intermediate_claim, level/L4, family/plain, variable/gdp-growth, variable/goods-trade-balance, country/us, where/us, instrument/tariffs]
---

# Tariffs cut the deficit by slowing growth

> Not the argument Trump makes for them

## Leads to
- **+1 supports** → [[Main claim the US demand shock was exported]] `main_claim`

## Rests on
- [[Tariffs act as a consumption tax]] `mechanism` **+1 supports** this
- [[Lower capex → lower imports]] `mechanism` **+1 supports** this
- [[Trade balance = saving − investment]] `hidden_assumption` **+1 licenses** this

## Subject

- **variable**: [[gdp-growth]], [[goods-trade-balance]]
- **country**: [[us]]
- **instrument**: [[tariffs]]

## Source
- Article: [[2020-02-26 Do tariffs change the trade balance, and who absorbed the Q4 US demand drop]]
- Authored map: `mermaid_code/setser_feb_26_20.mmd`
- Passage: p6 — _proposed `abstracts`, score 0.400; unreviewed, not a citation_
- Published: https://www.cfr.org/articles/us-shock-global-demand-q4-coronavirus
- Node `setser_feb_26_20#C1` · level L4 · type resolved by `class`
- Full chain: `python scripts/trace.py setser_feb_26_20#C1`
