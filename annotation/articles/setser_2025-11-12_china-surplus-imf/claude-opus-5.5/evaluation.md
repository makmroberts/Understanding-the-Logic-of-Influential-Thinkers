# Evaluation: setser_2025-11-12_china-surplus-imf / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 19, hand 14
- hand boxes found: 9/14 = 0.64 (0.39-0.84)
  - of which by a shared paragraph: 5; by role only (same slot): 4
- model boxes that match a hand box: 9/19 = 0.47 (0.27-0.68)
- matched with the same role: 9/9 = 1.00 (0.70-1.00)
- roles present, F1: 0.80
- boxes with an excerpt checked word for word: 18/19 = 0.95 (0.75-0.99)

## Links

- hand links between matched boxes that the model also draws: 3/8 = 0.38 (0.14-0.69)
- of those, the same relation: 3/3 = 1.00 (0.44-1.00)
- model links between matched boxes that the hand map also has: 3/5 = 0.60 (0.23-0.88)

## Facets (mean Jaccard on matched boxes)

- country: 0.78
- data_basis: 0.31
- instrument: 0.25
- variable: 0.35

Cost of this run: $0.1862. Review items: 7.

## Matched boxes

| model | hand | by | model claim | hand claim |
|---|---|---|---|---|
| QF caveat | QF caveat | paragraph | To be fair, the IMF does support pro-consumption reforms and bank recapitalization. | Caveat China's GDP data are too thin to confirm the net export math; the IMF does support  |
| X opposing_view | X opposing_view | paragraph | The view that Europe's surplus is nearly as large, so China deserves no special focus. | Opposing view The IMF's framing; the argument that Europe's surplus is almost as big |
| C3 intermediate_claim | C1 intermediate_claim | paragraph | Because the surplus looks small, the IMF treats China's problem as purely internal and rec | Intermediate claim China's surplus is massive and growing, yet IMF policy advice effective |
| E1 evidence_data | E1 evidence_data | paragraph | China's car exports above 6 million, export volumes up 40% against imports up 1%, a manufa | Data Export volumes up 40 percent since end-2019 versus imports up 1 percent; manufactured |
| E3 evidence_source | E2 evidence_source | slot | CPB data show China's export volumes outpacing global trade while Europe's shrink. | Studies and sources IMF External Sector Report 2025, October World Economic Outlook and 20 |
| K main_claim | K main_claim | slot | China's understated surplus leads the IMF to underplay China's role in global imbalances a | Main claim The IMF should recognize China's external imbalance and call for a fiscal expan |
| M1 mechanism | M1 mechanism | paragraph | Weak Chinese domestic demand frees spare capacity for export, and the low rates and weak c | Demand shortfall Weak domestic demand leaves spare capacity for exports; rate cuts lower y |
| P2 hidden_assumption | P3 hidden_assumption | slot | Customs trade data measure a country's true external imbalance better than balance of paym | Hidden assumption External balance is a legitimate policy target; exporting your way out o |
| Q question | Q question | slot | Why does the IMF fail to see China's huge surplus, and what does that miss cost in its pol | Question How big is China's surplus really, why does the IMF miss it, and what policy shou |

Unmatched model boxes: SCP (scope_choice), C1 (intermediate_claim), C2 (intermediate_claim), E2 (evidence_data), M2 (mechanism), SC (source_credibility), ANOM (anomaly), P1 (stated_assumption), REC (recommendation), M3 (mechanism)

Unmatched hand boxes: P1 (stated_assumption), P2 (stated_assumption), M2 (mechanism), M3 (mechanism), R1 (other_explanation)
