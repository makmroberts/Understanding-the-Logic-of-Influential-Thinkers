# Evaluation: setser_mar_31_20 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 27, hand 14
- hand boxes found: 11/14 = 0.79 (0.52-0.92)
  - of which by a shared paragraph: 8; by role only (same slot): 3
- model boxes that match a hand box: 11/27 = 0.41 (0.25-0.59)
- matched with the same role: 11/11 = 1.00 (0.74-1.00)
- roles present, F1: 0.96
- boxes with an excerpt checked word for word: 27/27 = 1.00 (0.88-1.00)

## Links

- hand links between matched boxes that the model also draws: 2/8 = 0.25 (0.07-0.59)
- of those, the same relation: 2/2 = 1.00 (0.34-1.00)
- model links between matched boxes that the hand map also has: 2/7 = 0.29 (0.08-0.64)

## Facets (mean Jaccard on matched boxes)

- bloc: 0.5
- country: 0.0
- data_basis: 0.5
- instrument: 0.28
- variable: 0.44

## Meaning (cross-encoder; same meaning at a score of 0.4 or more)

- matched pairs that say the same thing: 8/11 = 0.73 (0.43-0.90)
- hand boxes covered by a model box of the same role family: 9/14 = 0.64 (0.39-0.84)
  - matched, same meaning: 8; covered by another box of the family: 1
- hand boxes said by a model box under another role: 2
- hand boxes not found: 3

| role family | hand | model | matched, same meaning | covered in family | other role | not found |
|---|---|---|---|---|---|---|
| claim.final | 2 | 6 | 2 | 0 | 0 | 0 |
| claim.step | 2 | 5 | 2 | 0 | 0 | 0 |
| framing | 1 | 2 | 1 | 0 | 0 | 0 |
| grounds | 2 | 4 | 0 | 1 | 0 | 1 |
| qualifier | 1 | 2 | 1 | 0 | 0 | 0 |
| rebuttal | 1 | 1 | 1 | 0 | 0 | 0 |
| revision | 1 | 1 | 1 | 0 | 0 | 0 |
| warrant.mechanism | 2 | 3 | 0 | 0 | 0 | 2 |
| warrant.prior | 2 | 3 | 0 | 0 | 2 | 0 |

Cost of this run: $0.4011. Review items: 10.

## Matched boxes

| model | hand | by | meaning | model claim | hand claim |
|---|---|---|---|---|---|
| P4 revised_prior | P3 revised_prior | paragraph | 0.8 | The author's 2005 forecast with Roubini, that central banks would stop financing the U.S.  | Revised prior "contrary to a forecast that I made with Dr. Roubini back in 2005" — private |
| Q question | Q question | paragraph | 0.65 | How will the simultaneous shocks of 2020 affect different emerging economies, and what pol | Question Emerging economies face the same shocks — do they need the same response? |
| X opposing_view | X opposing_view | paragraph | 0.65 | Private creditors prefer full repayment and may resist maturity extensions. | Opposing view Private creditors would rather be paid — "this will take goodwill" |
| C1 intermediate_claim | C1 intermediate_claim | paragraph | 0.8 | Countries with strong external balance sheets can weather the shock by using their public  | Intermediate claim Countries with strong external balance sheets can weather this themselv |
| C5 case_type | C2 case_type | paragraph | 0.41 | Funding needs come in two kinds, short-term dollar trade finance and medium- to long-term  | Case type Three types — reserve-rich commodity exporters, Asian surplus creditors, weak ex |
| E4 evidence_source | E2 evidence_source | slot | 0.05 | Brender and Pisani, along with the author's Iceland conference paper, explain how the U.S. | Studies & sources Truman on IMF lending capacity; Landers, Lee and Morris on callable capi |
| K main_claim | K main_claim | slot | 0.55 | The shocks create many different emerging market crises: strong countries should self-insu | Main claim "Different problems require different solutions" — when private capital retreat |
| P3 hidden_assumption | P2 hidden_assumption | slot | 0.26 | Losses at the financial institutions of strong-balance-sheet countries can be absorbed dom | Hidden assumption The external balance sheet is the right thing to sort countries by |
| E1 evidence_data | E1 evidence_data | paragraph | 0.12 | Four simultaneous shocks hit emerging economies: an oil and commodity price collapse below | Data Brent under $25, below almost every exporter's breakeven; Saudi reserves ~$500bn; GCC |
| QF caveat | QF caveat | paragraph | 0.62 | An SDR allocation alone is insufficient because it is distributed by quota rather than nee | Caveat SDRs are allocated by quota rather than need, so they are insufficient alone; MDB c |
| REC4 recommendation | REC recommendation | paragraph | 0.53 | The IMF should make an SDR allocation to raise global reserves, with reserve-rich countrie | Recommendation Draw down buffers; central bank backstop plus swap lines; mobilise trade fi |

Unmatched model boxes: M1 (mechanism), M2 (mechanism), C4 (case_type), E2 (evidence_data), REC (recommendation), M3 (mechanism), E3 (evidence_data), REC2 (recommendation), C2 (intermediate_claim), P1 (stated_assumption), P2 (stated_assumption), C3 (intermediate_claim), REC3 (recommendation), REC5 (recommendation), QF2 (caveat), DF (deferred_question)

Unmatched hand boxes: P1 (stated_assumption), M1 (mechanism), M2 (mechanism)
