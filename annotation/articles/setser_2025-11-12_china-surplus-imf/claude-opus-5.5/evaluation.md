# Evaluation: setser_2025-11-12_china-surplus-imf / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 23, hand 14
- hand boxes found: 9/14 = 0.64 (0.39-0.84)
  - of which by a shared paragraph: 5; by role only (same slot): 4
- model boxes that match a hand box: 9/23 = 0.39 (0.22-0.59)
- matched with the same role: 9/9 = 1.00 (0.70-1.00)
- roles present, F1: 0.71
- boxes with an excerpt checked word for word: 22/23 = 0.96 (0.79-0.99)

## Links

- hand links between matched boxes that the model also draws: 2/8 = 0.25 (0.07-0.59)
- of those, the same relation: 2/2 = 1.00 (0.34-1.00)
- model links between matched boxes that the hand map also has: 2/2 = 1.00 (0.34-1.00)

## Facets (mean Jaccard on matched boxes)

- country: 0.89
- data_basis: 0.36
- instrument: 0.38
- variable: 0.31

## Meaning (cross-encoder; same meaning at a score of 0.4 or more)

- matched pairs that say the same thing: 4/9 = 0.44 (0.19-0.73)
- hand boxes covered by a model box of the same role family: 7/14 = 0.50 (0.27-0.73)
  - matched, same meaning: 4; covered by another box of the family: 3
- hand boxes said by a model box under another role: 3
- hand boxes not found: 4

| role family | hand | model | matched, same meaning | covered in family | other role | not found |
|---|---|---|---|---|---|---|
| backing | 0 | 1 | 0 | 0 | 0 | 0 |
| claim.final | 1 | 2 | 0 | 1 | 0 | 0 |
| claim.step | 1 | 3 | 0 | 1 | 0 | 0 |
| framing | 1 | 2 | 1 | 0 | 0 | 0 |
| grounds | 2 | 5 | 1 | 0 | 0 | 1 |
| qualifier | 1 | 2 | 0 | 0 | 1 | 0 |
| rebuttal | 2 | 1 | 1 | 0 | 0 | 1 |
| unassigned | 0 | 1 | 0 | 0 | 0 | 0 |
| warrant.mechanism | 3 | 3 | 1 | 1 | 1 | 0 |
| warrant.prior | 3 | 3 | 0 | 0 | 1 | 2 |

Cost of this run: $0.375. Review items: 4.

## Matched boxes

| model | hand | by | meaning | model claim | hand claim |
|---|---|---|---|---|---|
| QF caveat | QF caveat | paragraph | 0.33 | The IMF does back bank recapitalization to finish sold apartments and pro-consumption stru | Caveat China's GDP data are too thin to confirm the net export math; the IMF does support  |
| X opposing_view | X opposing_view | paragraph | 0.64 | Others argue that Europe's surplus is nearly as large as China's, so singling out China is | Opposing view The IMF's framing; the argument that Europe's surplus is almost as big |
| C2 intermediate_claim | C1 intermediate_claim | paragraph | 0.33 | Because the surplus looks small, the IMF treats China's problem as purely internal and ign | Intermediate claim China's surplus is massive and growing, yet IMF policy advice effective |
| E4 evidence_source | E2 evidence_source | slot | 0.18 | CPB data show China's export volumes outpacing global trade while Europe's shrink. | Studies and sources IMF External Sector Report 2025, October World Economic Outlook and 20 |
| K main_claim | K main_claim | slot | 0.39 | China's surplus is massive and is the central global imbalance; by relying on understated  | Main claim The IMF should recognize China's external imbalance and call for a fiscal expan |
| M1 mechanism | M1 mechanism | paragraph | 0.86 | Weak domestic demand frees capacity for export, and the resulting rate cuts, low yields an | Demand shortfall Weak domestic demand leaves spare capacity for exports; rate cuts lower y |
| P3 hidden_assumption | P3 hidden_assumption | slot | 0.01 | China's central government has the fiscal space to finance a large expansion without risk. | Hidden assumption External balance is a legitimate policy target; exporting your way out o |
| Q question | Q question | slot | 0.82 | Why does the IMF fail to see China's huge surplus clearly, and what does that blind spot c | Question How big is China's surplus really, why does the IMF miss it, and what policy shou |
| E3 evidence_data | E1 evidence_data | paragraph | 0.57 | Customs data show a manufactured-goods surplus above $2 trillion (10.5 percent of GDP, ove | Data Export volumes up 40 percent since end-2019 versus imports up 1 percent; manufactured |

Unmatched model boxes: E1 (evidence_data), E2 (evidence_data), P1 (stated_assumption), C1 (intermediate_claim), POS (position_map), SCP (scope_choice), E5 (evidence_discrepancy), M2 (mechanism), SC (source_credibility), ANOM (anomaly), P2 (stated_assumption), C3 (policy_reductio), REC (recommendation), M3 (mechanism)

Unmatched hand boxes: P1 (stated_assumption), P2 (stated_assumption), M2 (mechanism), M3 (mechanism), R1 (other_explanation)
