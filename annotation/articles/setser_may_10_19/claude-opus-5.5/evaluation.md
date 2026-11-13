# Evaluation: setser_may_10_19 / claude-opus-5.5

Compared with the hand-drawn map. Scores with 95% Wilson intervals.


## Boxes

- model 24, hand 23
- hand boxes found: 11/23 = 0.48 (0.29-0.67)
  - of which by a shared paragraph: 10; by role only (same slot): 1
- model boxes that match a hand box: 11/24 = 0.46 (0.28-0.65)
- matched with the same role: 9/11 = 0.82 (0.52-0.95)
- roles present, F1: 0.64
- boxes with an excerpt checked word for word: 23/24 = 0.96 (0.80-0.99)

## Links

- hand links between matched boxes that the model also draws: 3/4 = 0.75 (0.30-0.95)
- of those, the same relation: 2/3 = 0.67 (0.21-0.94)
- model links between matched boxes that the hand map also has: 3/4 = 0.75 (0.30-0.95)

## Facets (mean Jaccard on matched boxes)

- bloc: 0.5
- country: 0.68
- data_basis: 0.33
- instrument: 0.72
- variable: 0.42

Cost of this run: $0.229. Review items: 4.

## Matched boxes

| model | hand | by | model claim | hand claim |
|---|---|---|---|---|
| Q question | Q question | paragraph | With the trade deal collapsing and full U.S. tariffs looming, will China keep the yuan sta | If U.S.-China trade tensions escalate, will China keep the yuan stable or let it weaken? I |
| C2 intermediate_claim | C1 intermediate_claim | paragraph | China has ample dollars at the central bank and banks to manage its currency either way. | China has a genuine policy choice It is not mechanically forced into depreciation |
| C4 intermediate_claim | C4 intermediate_claim | paragraph | A weaker yuan would drag other Asian currencies down, pressure Turkey-like economies, and  | A weaker yuan redistributes trade pain Export-dependent economies outside China also come  |
| E1 evidence_data | D1 evidence_data | paragraph | Full tariffs would raise about $100–140 billion, roughly half a point of GDP fiscal tighte | Full tariffs would be substantial 25% on nearly $550B of imports could raise roughly $100– |
| E2 evidence_data | D6 evidence_data | paragraph | China's manufacturing surplus remains about $1 trillion, and a larger one would harm the w | Manufacturing surplus ~ $1T Further export-oriented adjustment would matter globally |
| E4 evidence_data | D3 evidence_data | paragraph | Intervention proxies show two-way state bank activity, with no sustained pressure either w | Recent yuan stability required little intervention No sustained pressure in either directi |
| K main_claim | K main_claim | slot | China will likely limit near-term yuan weakness while it tests whether a deal is still pos | Main claim: China's currency response is a strategic choice Beijing can defend stability o |
| M2 mechanism | M3 mechanism | paragraph | Even if tariffs and oil sanctions push China into a current account deficit, a credible st | Stability protects domestic confidence Avoiding a large currency move limits financial ins |
| M4 mechanism | M2 mechanism | paragraph | Depreciation risks provoking Trump into higher or broader tariffs. | Depreciation cushions exporters A weaker yuan offsets part of the tariff in dollar terms |
| E5 evidence_source | D2 evidence_data | paragraph | UBS estimates full tariffs plus retaliation could cut China's growth by 1.5 points; export | Large potential China growth hit UBS: full tariffs plus retaliation could cut growth by ab |
| X opposing_view | X counterpoint | paragraph | Critics overstated the weakness of the deal's currency stability commitment, which locked  | Case for stability China can support growth fiscally without risking a destabilizing curre |

Unmatched model boxes: POS (position_map), C1 (intermediate_claim), P1 (stated_assumption), M1 (mechanism), C3 (intermediate_claim), SCP (scope_choice), E3 (evidence_data), E6 (evidence_rival), P3 (hidden_assumption), C5 (case_type), M3 (mechanism), QF (caveat), P2 (stated_assumption)

Unmatched hand boxes: P1 (stated_assumption), P2 (stated_assumption), P3 (stated_assumption), D4 (evidence_data), D5 (evidence_data), M1 (mechanism), M4 (mechanism), C2 (intermediate_claim), C3 (intermediate_claim), QF (caveat), R1 (caveat), R2 (caveat)
