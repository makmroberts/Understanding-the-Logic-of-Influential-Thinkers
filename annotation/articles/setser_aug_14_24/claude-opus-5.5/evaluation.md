# Evaluation: setser_aug_14_24 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 22, hand 17
- hand boxes found: 14/17 = 0.82 (0.59-0.94)
  - of which by a shared paragraph: 11; by role only (same slot): 3
- model boxes that match a hand box: 14/22 = 0.64 (0.43-0.80)
- matched with the same role: 13/14 = 0.93 (0.69-0.99)
- roles present, F1: 0.94
- boxes with an excerpt checked word for word: 20/22 = 0.91 (0.72-0.97)

## Links

- hand links between matched boxes that the model also draws: 7/12 = 0.58 (0.32-0.81)
- of those, the same relation: 7/7 = 1.00 (0.65-1.00)
- model links between matched boxes that the hand map also has: 7/13 = 0.54 (0.29-0.77)

## Facets (mean Jaccard on matched boxes)

- country: 1.0
- data_basis: 0.54
- variable: 0.47

## Meaning (cross-encoder; same meaning at a score of 0.4 or more)

- matched pairs that say the same thing: 11/14 = 0.79 (0.52-0.92)
- hand boxes covered by a model box of the same role family: 13/17 = 0.76 (0.53-0.90)
  - matched, same meaning: 11; covered by another box of the family: 2
- hand boxes said by a model box under another role: 1
- hand boxes not found: 3

| role family | hand | model | matched, same meaning | covered in family | other role | not found |
|---|---|---|---|---|---|---|
| backing | 1 | 2 | 1 | 0 | 0 | 0 |
| claim.final | 3 | 3 | 3 | 0 | 0 | 0 |
| claim.step | 1 | 1 | 0 | 0 | 0 | 1 |
| framing | 2 | 2 | 2 | 0 | 0 | 0 |
| grounds | 4 | 4 | 3 | 1 | 0 | 0 |
| qualifier | 1 | 2 | 1 | 0 | 0 | 0 |
| rebuttal | 1 | 1 | 0 | 0 | 0 | 1 |
| warrant.mechanism | 2 | 2 | 1 | 0 | 1 | 0 |
| warrant.prior | 2 | 5 | 0 | 1 | 0 | 1 |

Cost of this run: $0.3508. Review items: 4.

## Matched boxes

| model | hand | by | meaning | model claim | hand claim |
|---|---|---|---|---|---|
| C1 intermediate_claim | C1 intermediate_claim | paragraph | 0.14 | A trade deficit arising from domestic production for the domestic market is economically m | Intermediate claim It makes no economic sense; the offsetting adjustment is absent; the se |
| DF deferred_question | DF deferred_question | paragraph | 0.56 | The puzzle of China's low interest income and large income deficit, despite higher global  | Deferred question The interest income anomaly is set aside "for a future blog" |
| K main_claim | K main_claim | paragraph | 0.62 | The fall in China's reported current account surplus since 2021 is mainly an artifact of a | Main claim The reported surplus is an artifact of a methodology change |
| RC reconstruction | RC reconstruction | paragraph | 0.6 | Correcting the goods data, the author estimates China's current account surplus at close t | Reconstruction Goods surplus understated by ~$300bn, over 1.5pp of GDP; true current accou |
| REC recommendation | REC recommendation | paragraph | 0.42 | The IMF and other global monitors should stop relying on China's reported current account  | Recommendation implied only — stop using the reported series |
| E3 evidence_source | E2 evidence_source | paragraph | 0.42 | The IMF staff report's Appendix VII confirms that factoryless manufacturing transactions h | Studies & sources IMF Article IV Appendix VII; consistent with Adam Wolf's work |
| E2 evidence_data | E1 evidence_data | paragraph | 0.6 | The BOP goods surplus is about $300 billion (over 1.5% of GDP) too small, and the Q2 curre | Data Reported current account ~$150bn below expectation in Q2 |
| E4 evidence_discrepancy | E4 evidence_discrepancy | slot | 0.4 | The goods divergence is not offset elsewhere in the current account; the gap between the c | Discrepancy Gap explodes from 2022; BoP imports exceed customs imports for the first time  |
| M1 mechanism | M1 mechanism | paragraph | 0.66 | Under factoryless manufacturing, a contract manufacturer's delivery to a foreign firm insi | Mechanism A "Factoryless" manufacturing — a sale to a non-resident is booked as an export  |
| Q question | Q question | slot | 0.8 | Why does China's balance of payments goods surplus diverge so sharply from its customs goo | Question Why does the reported current account diverge from the customs surplus, and which |
| QF2 caveat | QF caveat | paragraph | 0.68 | Because the income line offers no detail, the author cannot verify how profits and offsets | Caveat The income line carries no detail, so this cannot be checked from outside |
| SC2 source_credibility | SC source_credibility | paragraph | 0.45 | China has a history of opportune methodology changes, such as the 2015 tourism spending re | Source credibility The methodology was already changed at a convenient moment in 2015, and |
| X opposing_view | X opposing_view | slot | 0.36 | Many analysts take China's reported current account decline at face value as evidence of a | Opposing view Analysts and the IMF read the post-2021 decline as real |
| ID accounting_identity | P1 stated_assumption | paragraph | 0.27 | A reclassification that shifts profit offshore should be offset by changes in the income a | Stated assumption The balance-of-payments surplus should exceed customs; a methodology cha |

Unmatched model boxes: P1 (stated_assumption), P2 (stated_assumption), P3 (hidden_assumption), P4 (hidden_assumption), E1 (evidence_data), M2 (mechanism), SC (source_credibility), QF (caveat)

Unmatched hand boxes: P2 (hidden_assumption), E3 (evidence_rival), M2 (mechanism)
