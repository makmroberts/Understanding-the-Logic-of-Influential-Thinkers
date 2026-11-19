# Evaluation: setser_may_10_19 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 25, hand 23
- hand boxes found: 8/23 = 0.35 (0.19-0.55)
  - of which by a shared paragraph: 7; by role only (same slot): 1
- model boxes that match a hand box: 8/25 = 0.32 (0.17-0.52)
- matched with the same role: 6/8 = 0.75 (0.41-0.93)
- roles present, F1: 0.58
- boxes with an excerpt checked word for word: 24/25 = 0.96 (0.80-0.99)

## Links

- hand links between matched boxes that the model also draws: 1/1 = 1.00 (0.21-1.00)
- of those, the same relation: 1/1 = 1.00 (0.21-1.00)
- model links between matched boxes that the hand map also has: 1/2 = 0.50 (0.09-0.91)

## Facets (mean Jaccard on matched boxes)

- bloc: 0.0
- country: 0.56
- data_basis: 1.0
- instrument: 0.71
- variable: 0.52

## Meaning (cross-encoder; same meaning at a score of 0.4 or more)

- matched pairs that say the same thing: 5/8 = 0.62 (0.31-0.86)
- hand boxes covered by a model box of the same role family: 9/23 = 0.39 (0.22-0.59)
  - matched, same meaning: 5; covered by another box of the family: 4
- hand boxes said by a model box under another role: 2
- hand boxes not found: 12

| role family | hand | model | matched, same meaning | covered in family | other role | not found |
|---|---|---|---|---|---|---|
| backing | 0 | 1 | 0 | 0 | 0 | 0 |
| claim.final | 1 | 1 | 1 | 0 | 0 | 0 |
| claim.step | 4 | 5 | 0 | 0 | 0 | 4 |
| framing | 1 | 1 | 1 | 0 | 0 | 0 |
| grounds | 6 | 4 | 3 | 1 | 0 | 2 |
| qualifier | 3 | 3 | 0 | 1 | 1 | 1 |
| rebuttal | 1 | 2 | 0 | 0 | 0 | 1 |
| unassigned | 0 | 1 | 0 | 0 | 0 | 0 |
| warrant.mechanism | 4 | 3 | 0 | 1 | 1 | 2 |
| warrant.prior | 3 | 4 | 0 | 1 | 0 | 2 |

Cost of this run: $0.2448. Review items: 4.

## Matched boxes

| model | hand | by | meaning | model claim | hand claim |
|---|---|---|---|---|---|
| Q question | Q question | paragraph | 0.8 | If the US imposes the full threatened tariffs, will China hold the yuan stable or let it w | If U.S.-China trade tensions escalate, will China keep the yuan stable or let it weaken? I |
| C4 intermediate_claim | C4 intermediate_claim | paragraph | 0.35 | A weaker yuan would spread China's trade pain globally: other Asian currencies would follo | A weaker yuan redistributes trade pain Export-dependent economies outside China also come  |
| E1 evidence_data | D1 evidence_data | paragraph | 0.74 | Full 25 percent tariffs on about $550 billion of imports would raise $100 to 140 billion,  | Full tariffs would be substantial 25% on nearly $550B of imports could raise roughly $100– |
| E3 evidence_data | D3 evidence_data | paragraph | 0.58 | Intervention proxies show state bank purchases and sales alternating, with no sustained pr | Recent yuan stability required little intervention No sustained pressure in either directi |
| K main_claim | K main_claim | slot | 0.46 | China can choose either path, but it will most likely limit near-term depreciation while i | Main claim: China's currency response is a strategic choice Beijing can defend stability o |
| M3 mechanism | M2 mechanism | paragraph | 0.15 | Depreciation could provoke Trump into higher or broader tariffs, so a major move is better | Depreciation cushions exporters A weaker yuan offsets part of the tariff in dollar terms |
| E4 evidence_source | D2 evidence_data | paragraph | 0.7 | UBS estimates full tariffs plus retaliation could cut China's growth by 1.5 points, with e | Large potential China growth hit UBS: full tariffs plus retaliation could cut growth by ab |
| X opposing_view | X counterpoint | paragraph | 0.38 | Critics overstated the problems with China's reported currency-stability commitment, since | Case for stability China can support growth fiscally without risking a destabilizing curre |

Unmatched model boxes: ANOM (anomaly), R1 (other_explanation), C1 (intermediate_claim), P1 (stated_assumption), C2 (intermediate_claim), P2 (stated_assumption), SCP (scope_choice), E2 (evidence_data), SC (source_credibility), ID (accounting_identity), C3 (intermediate_claim), C5 (case_type), M1 (mechanism), QF (caveat), M2 (mechanism), P3 (hidden_assumption), QF2 (caveat)

Unmatched hand boxes: P1 (stated_assumption), P2 (stated_assumption), P3 (stated_assumption), D4 (evidence_data), D5 (evidence_data), D6 (evidence_data), M1 (mechanism), M3 (mechanism), M4 (mechanism), C1 (intermediate_claim), C2 (intermediate_claim), C3 (intermediate_claim), QF (caveat), R1 (caveat), R2 (caveat)
