# Evaluation: setser_2025-09-12_trump-shock-that-wasnt / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 24, hand 15
- hand boxes found: 10/15 = 0.67 (0.42-0.85)
  - of which by a shared paragraph: 8; by role only (same slot): 2
- model boxes that match a hand box: 10/24 = 0.42 (0.24-0.61)
- matched with the same role: 10/10 = 1.00 (0.72-1.00)
- roles present, F1: 0.82
- boxes with an excerpt checked word for word: 22/24 = 0.92 (0.74-0.98)

## Links

- hand links between matched boxes that the model also draws: 2/9 = 0.22 (0.06-0.55)
- of those, the same relation: 2/2 = 1.00 (0.34-1.00)
- model links between matched boxes that the hand map also has: 2/3 = 0.67 (0.21-0.94)

## Facets (mean Jaccard on matched boxes)

- bloc: 0.5
- country: 0.75
- data_basis: 0.0
- instrument: 0.78
- variable: 0.47

Cost of this run: $0.2008. Review items: 7.

## Matched boxes

| model | hand | by | model claim | hand claim |
|---|---|---|---|---|
| Q question | Q question | paragraph | Why has the large shock to trade rules from Trump's tariffs produced only a small shock to | Question Have Trump's tariffs actually shocked trade flows and the global economy? |
| K main_claim | K main_claim | slot | The tariff shock to trade rules has been far larger than the shock to trade flows, at leas | Main claim The Trump shock to trade flows has not happened yet, though a modest impact sho |
| M1 mechanism | M1 mechanism | paragraph | The headline volatility comes from pharmaceutical stockpiling and tax-driven trade, and fr | Front-running Pharmaceutical stockpiling (distorted by tax) and gold flows drive the headl |
| M3 mechanism | M3 mechanism | paragraph | An AI data-center investment boom has pushed electronics imports up, with imports from Tai | Artificial intelligence investment The data center buildout pushes electronics imports up |
| P1 stated_assumption | P1 stated_assumption | paragraph | The import response to a broad price change such as an exchange rate move is about 0.3 to  | Stated assumption A global tariff works like an exchange rate move: import elasticity of a |
| X opposing_view | X opposing_view | slot | The elasticity of about 2 seen in the first-term China tariffs overstates the effect of a  | Opposing view Reading headline volatility as tariffs crushing trade |
| M2 mechanism | M2 mechanism | paragraph | Bilateral tariffs mainly reroute trade through relocated final assembly rather than reduci | Trade diversion Imports shift from China to Taiwan and Southeast Asia as final assembly re |
| M4 mechanism | M4 mechanism | paragraph | Foreign exporters can offset lost U.S. sales by taking market share from U.S. exporters bu | Elasticity math A 15 percent tariff times a 0.3 to 0.4 elasticity cuts imports 5 to 6 perc |
| QF2 caveat | QF caveat | paragraph | The verdict may not hold, because the August deals raised tariffs sharply and their effect | Caveat August deals doubled tariffs on Southeast Asia relative to April; fall data may sho |
| E1 evidence_data | E1 evidence_data | paragraph | Tariff rates now range from 50% for India and Brazil to 10% for Australia and the UK, with | Data Annualized trade deficit peaked at $2 trillion in March, fell to $1 trillion, then re |

Unmatched model boxes: C1 (intermediate_claim), E2 (evidence_data), SCP (scope_choice), P2 (hidden_assumption), E3 (evidence_data), E4 (evidence_data), C2 (intermediate_claim), C3 (intermediate_claim), E5 (evidence_data), C4 (intermediate_claim), QF (caveat), E6 (evidence_data), DF (deferred_question), P3 (hidden_assumption)

Unmatched hand boxes: P2 (stated_assumption), P3 (hidden_assumption), E2 (evidence_source), C1 (intermediate_claim), R1 (other_explanation)
