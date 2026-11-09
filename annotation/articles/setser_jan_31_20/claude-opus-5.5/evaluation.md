# Evaluation: setser_jan_31_20 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 30, hand 14
- hand boxes found: 12/14 = 0.86 (0.60-0.96)
  - of which by a shared paragraph: 9; by role only (same slot): 3
- model boxes that match a hand box: 12/30 = 0.40 (0.25-0.58)
- matched with the same role: 12/12 = 1.00 (0.76-1.00)
- roles present, F1: 0.90
- boxes with an excerpt checked word for word: 29/30 = 0.97 (0.83-0.99)

## Links

- hand links between matched boxes that the model also draws: 1/4 = 0.25 (0.05-0.70)
- of those, the same relation: 1/1 = 1.00 (0.21-1.00)
- model links between matched boxes that the hand map also has: 1/6 = 0.17 (0.03-0.56)

## Facets (mean Jaccard on matched boxes)

- bloc: 0.0
- country: 0.71
- data_basis: 0.0
- instrument: 0.17
- variable: 0.21

Cost of this run: $0.2501. Review items: 11.

## Matched boxes

| model | hand | by | model claim | hand claim |
|---|---|---|---|---|
| K main_claim | K main_claim | paragraph | China's response had five features: it shielded industrial policy, used the currency witho | Main claim China can meet its 2020 commitments — and that is precisely the risk. "What Chi |
| P3 revised_prior | P3 revised_prior | paragraph | The author expected the global soy market to absorb China's boycott and was surprised that | Revised prior "I was surprised by the size of China's impact... I thought U.S. soy would p |
| Q question | Q question | paragraph | How did China respond to Trump's tariff pressure, and what does that response imply for th | Question How did China choose to respond to tariff pressure, and what does that reveal abo |
| R1 other_explanation | R1 other_explanation | paragraph | China may have spared U.S. manufactures because the remaining imports were ones it needed, | Other explanation Why were manufactures spared? "I am not quite sure why this is the case" |
| SC source_credibility | SC source_credibility | paragraph | The author distrusts Chinese official data because the different series never fully reconc | Source credibility "Chinese data never quite fully lines up, which bothers me more than mo |
| E3 evidence_source | E2 evidence_source | slot | The Economist argued that Trump's managed trade rewards China for diverting imports from U | Studies & sources His own Senate testimony; Toloui on balance-sheet policy; the Economist  |
| M3 mechanism | M1 mechanism | paragraph | The depreciation caused no panic because of tight capital controls, no carry trades to unw | Mechanism A Outflow controls and the absence of carry-trade leverage prevented a 2015-styl |
| M5 mechanism | M2 mechanism | paragraph | Because the Fed can expand its balance sheet or cap yields, a Chinese sale of Treasuries w | Mechanism B Treasuries carry no leverage — if China pushed yields up, the Fed would simply |
| P1 stated_assumption | P1 stated_assumption | slot | Fungible commodities such as crude and NGLs can be rerouted to other buyers, which limits  | Stated assumption Industrial policy is non-negotiable; the state can direct commodity purc |
| P2 hidden_assumption | P2 hidden_assumption | slot | China acts as a rational strategic actor that weighs whether a retaliatory tool will work  | Hidden assumption The capacity to deliver purchases is the same capacity that can withdraw |
| QF caveat | QF caveat | paragraph | Import substitution will not visibly reduce China's imports in 2020, because jet engines,  | Caveat Tech decoupling will not bite in 2020: Boeing's own problems, no indigenous jet eng |
| X2 opposing_view | X opposing_view | paragraph | The conventional legal approach to Chinese industrial policy, such as Obama's indigenous-i | Opposing view Both approaches carry costs — managed trade rewards diversion away from alli |

Unmatched model boxes: C1 (intermediate_claim), M1 (mechanism), C2 (intermediate_claim), E1 (evidence_data), M2 (mechanism), ANOM (anomaly), E4 (evidence_rival), C3 (intermediate_claim), M4 (mechanism), C4 (intermediate_claim), SCP (scope_choice), X (opposing_view), QF2 (caveat), C5 (intermediate_claim), E2 (evidence_data), M6 (mechanism), C6 (intermediate_claim), C7 (intermediate_claim)

Unmatched hand boxes: E1 (evidence_data), C1 (intermediate_claim)
