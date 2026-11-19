# Evaluation: setser_jan_31_20 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 25, hand 14
- hand boxes found: 12/14 = 0.86 (0.60-0.96)
  - of which by a shared paragraph: 9; by role only (same slot): 3
- model boxes that match a hand box: 12/25 = 0.48 (0.30-0.67)
- matched with the same role: 12/12 = 1.00 (0.76-1.00)
- roles present, F1: 0.93
- boxes with an excerpt checked word for word: 24/25 = 0.96 (0.80-0.99)

## Links

- hand links between matched boxes that the model also draws: 1/5 = 0.20 (0.04-0.62)
- of those, the same relation: 1/1 = 1.00 (0.21-1.00)
- model links between matched boxes that the hand map also has: 1/6 = 0.17 (0.03-0.56)

## Facets (mean Jaccard on matched boxes)

- country: 0.75
- data_basis: 0.0
- instrument: 0.05
- variable: 0.25

## Meaning (cross-encoder; same meaning at a score of 0.4 or more)

- matched pairs that say the same thing: 7/12 = 0.58 (0.32-0.81)
- hand boxes covered by a model box of the same role family: 8/14 = 0.57 (0.33-0.79)
  - matched, same meaning: 7; covered by another box of the family: 1
- hand boxes said by a model box under another role: 2
- hand boxes not found: 4

| role family | hand | model | matched, same meaning | covered in family | other role | not found |
|---|---|---|---|---|---|---|
| backing | 1 | 1 | 1 | 0 | 0 | 0 |
| claim.final | 1 | 2 | 0 | 0 | 0 | 1 |
| claim.step | 1 | 3 | 0 | 0 | 1 | 0 |
| framing | 1 | 1 | 1 | 0 | 0 | 0 |
| grounds | 2 | 6 | 2 | 0 | 0 | 0 |
| qualifier | 1 | 3 | 0 | 0 | 0 | 1 |
| rebuttal | 2 | 2 | 1 | 0 | 1 | 0 |
| revision | 1 | 1 | 1 | 0 | 0 | 0 |
| unassigned | 0 | 1 | 0 | 0 | 0 | 0 |
| warrant.mechanism | 2 | 3 | 1 | 1 | 0 | 0 |
| warrant.prior | 2 | 2 | 0 | 0 | 0 | 2 |

Cost of this run: $0.3708. Review items: 10.

## Matched boxes

| model | hand | by | meaning | model claim | hand claim |
|---|---|---|---|---|---|
| P3 revised_prior | P3 revised_prior | paragraph | 0.57 | The author expected US soybeans to find other buyers easily and was surprised by how large | Revised prior "I was surprised by the size of China's impact... I thought U.S. soy would p |
| Q question | Q question | paragraph | 0.75 | How did China respond to Trump's tariff pressure in phase one of the trade war, and what d | Question How did China choose to respond to tariff pressure, and what does that reveal abo |
| R1 other_explanation | R1 other_explanation | paragraph | 0.53 | The author offers two possible reasons China spared US manufactures, without choosing betw | Other explanation Why were manufactures spared? "I am not quite sure why this is the case" |
| SC source_credibility | SC source_credibility | paragraph | 0.69 | Chinese official data never fully reconcile, which reduces confidence in the reserve measu | Source credibility "Chinese data never quite fully lines up, which bothers me more than mo |
| E5 evidence_source | E2 evidence_source | paragraph | 0.4 | The author cites an Economist article for laying out the disadvantages of both managed tra | Studies & sources His own Senate testimony; Toloui on balance-sheet policy; the Economist  |
| E2 evidence_data | E1 evidence_data | paragraph | 0.42 | China did not dump Treasuries: holdings fell only slightly once Belgian custodial accounts | Data Yuan -8% vs USD and -4% vs basket; Treasury holdings flat once Belgian accounts are c |
| K2 main_claim | K main_claim | paragraph | 0.15 | Managed trade makes US farmers hostages: the price of challenging Chinese industrial polic | Main claim China can meet its 2020 commitments — and that is precisely the risk. "What Chi |
| P1 stated_assumption | P1 stated_assumption | slot | 0.01 | The author takes as given that modern central banks will use balance sheet expansion and y | Stated assumption Industrial policy is non-negotiable; the state can direct commodity purc |
| P2 hidden_assumption | P2 hidden_assumption | slot | 0.01 | The US will eventually have to confront Chinese industrial policy again, since phase one d | Hidden assumption The capacity to deliver purchases is the same capacity that can withdraw |
| QF caveat | QF caveat | paragraph | 0.05 | The effects of import substitution are long-run and will not significantly affect China's  | Caveat Tech decoupling will not bite in 2020: Boeing's own problems, no indigenous jet eng |
| X opposing_view | X opposing_view | slot | 0.01 | The common view holds that China retaliated broadly against US manufactured exports. | Opposing view Both approaches carry costs — managed trade rewards diversion away from alli |
| M3 mechanism | M2 mechanism | paragraph | 0.65 | Selling Treasuries gives China little leverage because the Fed can offset any rise in yiel | Mechanism B Treasuries carry no leverage — if China pushed yields up, the Fed would simply |

Unmatched model boxes: K (main_claim), C1 (intermediate_claim), M1 (mechanism), E1 (evidence_data), M2 (mechanism), ANOM (anomaly), E6 (evidence_discrepancy), E3 (evidence_data), QF2 (caveat), C2 (intermediate_claim), E4 (evidence_data), C3 (intermediate_claim), QF3 (caveat)

Unmatched hand boxes: M1 (mechanism), C1 (intermediate_claim)
