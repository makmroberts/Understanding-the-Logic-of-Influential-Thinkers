---
type: mechanism
level: L3
date: 2025-07-28
article: "China is also Fighting a Trade War with Europe (and Winning)"
doc: setser_2025-07-28_china-eu-trade-war
node_id: M2
family: meta
relation_sources: [arrow]
variable: [nominal-exchange-rate, tariff-rate]
country_subject: [china]
country_counterpart: [euro-area]
instrument: [fx-intervention, tariffs]
bilateral: true
tags: [type/mechanism, level/L3, family/meta, variable/nominal-exchange-rate, variable/tariff-rate, country/china, where/china, country/euro-area, where/euro-area, instrument/fx-intervention, instrument/tariffs, shape/bilateral]
---

# Weak currency

> State banks keep the yuan weak; its fall against the euro has roughly offset the EU's 17 percent countervailing duty on BYD

## Leads to
- **+1 supports** → [[The second China shock is eroding Europe's core export sectors and is large enough to matter for the whole economy]] `intermediate_claim`

## Rests on
- [[China's trade war tools are industrial policy and a weak currency, not tariffs]] `stated_assumption` **+1 supports** this
- [[European exports to China down about 0.5 percentage points of European GDP; EU trade deficit with China set to double]] `evidence_data` **+1 supports** this

## Subject

- **variable**: [[nominal-exchange-rate]], [[tariff-rate]]
- **country**: [[euro-area]] _(counterpart)_, [[china]]
- **instrument**: [[fx-intervention]], [[tariffs]]

## Source
- Article: [[2025-07-28 China is also Fighting a Trade War with Europe (and Winning)]]
- Authored map: `mermaid_code/setser_2025-07-28_china-eu-trade-war.mmd`
- Passage: **p27** — **states**, anchored on `17percent`, a literal the claim and the paragraph share
- Published: https://www.cfr.org/articles/china-also-fighting-trade-war-europe-and-winning
- Node `setser_2025-07-28_china-eu-trade-war#M2` · level L3 · type resolved by `class`
- Full chain: `python scripts/trace.py setser_2025-07-28_china-eu-trade-war#M2`
