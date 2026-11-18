# Evaluation: setser_jun_14_19 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 23, hand 22
- hand boxes found: 9/22 = 0.41 (0.23-0.61)
  - of which by a shared paragraph: 9; by role only (same slot): 0
- model boxes that match a hand box: 9/23 = 0.39 (0.22-0.59)
- matched with the same role: 6/9 = 0.67 (0.35-0.88)
- roles present, F1: 0.64
- boxes with an excerpt checked word for word: 22/23 = 0.96 (0.79-0.99)

## Links

- hand links between matched boxes that the model also draws: -
- of those, the same relation: -
- model links between matched boxes that the hand map also has: 0/5 = 0.00 (0.00-0.43)

## Facets (mean Jaccard on matched boxes)

- country: 0.89
- data_basis: 0.33
- instrument: 0.88
- variable: 0.35

Cost of this run: $0.2213. Review items: 6.

## Matched boxes

| model | hand | by | model claim | hand claim |
|---|---|---|---|---|
| K main_claim | K main_claim | paragraph | China's retaliation has so far bitten mainly through commodities; its manufacturing tariff | Main claim: don't equate bilateral trade with aggregate impact The economic effect of tari |
| Q question | Q question | paragraph | Why have China's retaliatory tariffs crushed U.S. commodity exports while barely denting U | Why did China's tariffs devastate some U.S. exports but have limited effects on others? Wh |
| C3 intermediate_claim | C2 intermediate_claim | paragraph | Oil exports to China fell to near zero but total U.S. oil exports and pipeline investment  | Oil retaliation mostly redirected trade Bilateral trade fell without much aggregate effect |
| E1 evidence_data | D1 evidence_data | paragraph | Soybeans are ~10% of U.S. exports to China; commodity exports fell over 60% while manufact | Commodity exports to China down >60% Much larger decline than manufacturing exports |
| M2 mechanism | M1 mechanism | paragraph | China lacks good targets because many U.S. manufactured imports have no domestic substitut | Few alternative buyers magnify the shock Lost Chinese demand becomes lost total exports |
| QF2 caveat | QF1 caveat | paragraph | The modest manufacturing elasticity may partly reflect untariffed goods in the aggregate,  | Coverage caveat China had not tariffed all major U.S. manufacturing exports |
| DF deferred_question | QF2 caveat | paragraph | The overall impact of China's retaliation on the U.S. economy remains an open question. | Timing caveat China may have preserved targets for future retaliation |
| E3 evidence_source | D4 evidence_data | paragraph | Chad Bown's work shows China tariffed 55% of U.S. exports, raised its effective tariff fro | Auto exports responded to the tariff Exports fell, then rebounded when China suspended it |
| QF caveat | R1 counterpoint | paragraph | U.S. auto exports to China would likely fall anyway as German firms localize production in | Auto counterfactual SUV demand and production localization also affected output |

Unmatched model boxes: P3 (revised_prior), P1 (stated_assumption), C1 (intermediate_claim), R1 (other_explanation), M1 (mechanism), M3 (mechanism), E2 (evidence_data), X (opposing_view), M4 (mechanism), R2 (other_explanation), C2 (intermediate_claim), C4 (intermediate_claim), P2 (hidden_assumption), REC (recommendation)

Unmatched hand boxes: P1 (stated_assumption), P2 (stated_assumption), P3 (stated_assumption), D2 (evidence_data), D3 (evidence_data), D5 (evidence_data), D6 (evidence_data), M2 (mechanism), M3 (mechanism), M4 (mechanism), C1 (intermediate_claim), C3 (intermediate_claim), C4 (intermediate_claim)
