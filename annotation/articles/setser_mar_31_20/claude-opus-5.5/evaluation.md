# Evaluation: setser_mar_31_20 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 20, hand 14
- hand boxes found: 11/14 = 0.79 (0.52-0.92)
  - of which by a shared paragraph: 10; by role only (same slot): 1
- model boxes that match a hand box: 11/20 = 0.55 (0.34-0.74)
- matched with the same role: 11/11 = 1.00 (0.74-1.00)
- roles present, F1: 1.00
- boxes with an excerpt checked word for word: 20/20 = 1.00 (0.84-1.00)

## Links

- hand links between matched boxes that the model also draws: 4/8 = 0.50 (0.22-0.78)
- of those, the same relation: 4/4 = 1.00 (0.51-1.00)
- model links between matched boxes that the hand map also has: 4/8 = 0.50 (0.22-0.78)

## Facets (mean Jaccard on matched boxes)

- bloc: 0.23
- country: 0.0
- data_basis: 0.0
- instrument: 0.56
- variable: 0.52

Cost of this run: $0.2059. Review items: 5.

## Matched boxes

| model | hand | by | model claim | hand claim |
|---|---|---|---|---|
| C3 case_type | C2 case_type | paragraph | Funding needs come in two types: short-term dollar trade finance, and longer-term balance  | Case type Three types — reserve-rich commodity exporters, Asian surplus creditors, weak ex |
| E4 evidence_source | E2 evidence_source | paragraph | The BIS (Carstens, Shin), Truman, CGD (Landers, Lee, Morris), Hagan and Buchheit, Brender  | Studies & sources Truman on IMF lending capacity; Landers, Lee and Morris on callable capi |
| K main_claim | K main_claim | paragraph | Emerging markets face many distinct crises, not one, and the official sector must step in  | Main claim "Different problems require different solutions" — when private capital retreat |
| P4 revised_prior | P3 revised_prior | paragraph | He and Roubini forecast in 2005 that central banks would stop financing the U.S. deficit f | Revised prior "contrary to a forecast that I made with Dr. Roubini back in 2005" — private |
| Q question | Q question | paragraph | Given a set of simultaneous global shocks hitting emerging economies, how will their impac | Question Emerging economies face the same shocks — do they need the same response? |
| REC recommendation | REC recommendation | paragraph | The IMF should issue an SDR allocation and get more lending resources; MDBs should use cal | Recommendation Draw down buffers; central bank backstop plus swap lines; mobilise trade fi |
| X opposing_view | X opposing_view | paragraph | Private creditors would prefer full payment, but voluntary extension beats default. | Opposing view Private creditors would rather be paid — "this will take goodwill" |
| C1 intermediate_claim | C1 intermediate_claim | paragraph | Strong-balance-sheet countries can weather the storm by using public balance sheets and Fe | Intermediate claim Countries with strong external balance sheets can weather this themselv |
| P3 hidden_assumption | P2 hidden_assumption | slot | A creditor country's losses on its institutions can be absorbed domestically, so it faces  | Hidden assumption The external balance sheet is the right thing to sort countries by |
| E1 evidence_data | E1 evidence_data | paragraph | Four shocks hit at once: an oil and commodity price collapse, a manufacturing trade shock  | Data Brent under $25, below almost every exporter's breakeven; Saudi reserves ~$500bn; GCC |
| QF caveat | QF caveat | paragraph | An SDR allocation alone is insufficient because it goes by quota rather than need. | Caveat SDRs are allocated by quota rather than need, so they are insufficient alone; MDB c |

Unmatched model boxes: M1 (mechanism), M2 (mechanism), P1 (stated_assumption), E2 (evidence_data), M3 (mechanism), C2 (intermediate_claim), E3 (evidence_data), P2 (stated_assumption), QF2 (caveat)

Unmatched hand boxes: P1 (stated_assumption), M1 (mechanism), M2 (mechanism)
