# Evaluation: setser_jun_14_19 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 24, hand 22
- hand boxes found: 10/22 = 0.45 (0.27-0.65)
  - of which by a shared paragraph: 10; by role only (same slot): 0
- model boxes that match a hand box: 10/24 = 0.42 (0.24-0.61)
- matched with the same role: 7/10 = 0.70 (0.40-0.89)
- roles present, F1: 0.64
- boxes with an excerpt checked word for word: 22/24 = 0.92 (0.74-0.98)

## Links

- hand links between matched boxes that the model also draws: 0/1 = 0.00 (0.00-0.79)
- of those, the same relation: -
- model links between matched boxes that the hand map also has: 0/5 = 0.00 (0.00-0.43)

## Facets (mean Jaccard on matched boxes)

- country: 0.9
- data_basis: 0.67
- instrument: 0.61
- variable: 0.32

## Meaning (cross-encoder; same meaning at a score of 0.4 or more)

- matched pairs that say the same thing: 2/10 = 0.20 (0.06-0.51)
- hand boxes covered by a model box of the same role family: 5/22 = 0.23 (0.10-0.43)
  - matched, same meaning: 2; covered by another box of the family: 3
- hand boxes said by a model box under another role: 1
- hand boxes not found: 16

| role family | hand | model | matched, same meaning | covered in family | other role | not found |
|---|---|---|---|---|---|---|
| claim.final | 1 | 1 | 0 | 0 | 0 | 1 |
| claim.step | 4 | 1 | 0 | 0 | 0 | 4 |
| framing | 1 | 2 | 1 | 0 | 0 | 0 |
| grounds | 6 | 7 | 1 | 3 | 0 | 2 |
| qualifier | 2 | 3 | 0 | 0 | 1 | 1 |
| rebuttal | 1 | 3 | 0 | 0 | 0 | 1 |
| revision | 0 | 1 | 0 | 0 | 0 | 0 |
| warrant.mechanism | 4 | 4 | 0 | 0 | 0 | 4 |
| warrant.prior | 3 | 2 | 0 | 0 | 0 | 3 |

Cost of this run: $0.2245. Review items: 11.

## Matched boxes

| model | hand | by | meaning | model claim | hand claim |
|---|---|---|---|---|---|
| K main_claim | K main_claim | paragraph | 0.11 | China's retaliation has mainly hurt U.S. commodity exports, has been largely ineffective a | Main claim: don't equate bilateral trade with aggregate impact The economic effect of tari |
| Q question | Q question | paragraph | 0.73 | Why have China's retaliatory tariffs hit U.S. commodity exports hard but had little visibl | Why did China's tariffs devastate some U.S. exports but have limited effects on others? Wh |
| C1 intermediate_claim | C1 intermediate_claim | paragraph | 0.38 | Across soy, oil and autos, tariffs cut bilateral trade, but only in soy did they cause rea | Soy retaliation was unusually effective Bilateral losses became aggregate export losses |
| E1 evidence_data | D1 evidence_data | paragraph | 0.38 | U.S. commodity exports to China fell more than 60 percent, while manufacturing exports sho | Commodity exports to China down >60% Much larger decline than manufacturing exports |
| E5 evidence_data | D3 evidence_data | paragraph | 0.61 | Oil exports to China fell near zero but overall U.S. oil exports and Permian pipeline inve | Oil exports to China collapsed But total U.S. oil exports were largely unaffected |
| M2 mechanism | M1 mechanism | paragraph | 0.19 | China lacks good manufacturing targets because many U.S. imports have no substitute or fee | Few alternative buyers magnify the shock Lost Chinese demand becomes lost total exports |
| QF2 caveat | QF1 caveat | paragraph | 0.3 | The modest implied manufacturing elasticity may be understated because untariffed goods we | Coverage caveat China had not tariffed all major U.S. manufacturing exports |
| DF deferred_question | QF2 caveat | paragraph | 0.38 | The full economic impact of China's retaliation remains an open question. | Timing caveat China may have preserved targets for future retaliation |
| E7 evidence_source | D4 evidence_data | paragraph | 0.25 | Bown's work shows China tariffed 55 percent of U.S. exports, raising the average tariff fr | Auto exports responded to the tariff Exports fell, then rebounded when China suspended it |
| QF caveat | R1 counterpoint | paragraph | 0.24 | Auto exports to China would probably have fallen anyway as German firms localize productio | Auto counterfactual SUV demand and production localization also affected output |

Unmatched model boxes: P3 (revised_prior), E2 (evidence_data), R1 (other_explanation), M1 (mechanism), E3 (evidence_data), X (opposing_view), P1 (stated_assumption), R2 (other_explanation), E4 (evidence_data), M3 (mechanism), E6 (evidence_data), M4 (mechanism), P2 (hidden_assumption), SCP (scope_choice)

Unmatched hand boxes: P1 (stated_assumption), P2 (stated_assumption), P3 (stated_assumption), D2 (evidence_data), D5 (evidence_data), D6 (evidence_data), M2 (mechanism), M3 (mechanism), M4 (mechanism), C2 (intermediate_claim), C3 (intermediate_claim), C4 (intermediate_claim)
