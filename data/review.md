# Parse review

20 documents -> 358 nodes, 340 edges.

## Defaults applied - these are conventions, not authored decisions

- **201 of 340 edges carry no label** in the source and took `edge_default_solid` (`supports`). An unlabelled solid arrow meaning support is the drawing convention across all 20 maps, but it is still a default: only 139 edges state their type explicitly.
- Node types resolved by: 188 from class, 148 from header, 22 from l6_keyword. A type resolved by `level` alone is the weakest inference - see the `type_source` column in nodes.csv.

## Nodes in no edge (19)

Mostly Level 0 question nodes: the schema says L0 `==>|frames|` L1, but every article map draws that link with `~~~`, which is layout-only and carries no meaning. The question is therefore not connected to the argument it frames. Worth a schema decision rather than a parser fix.

- `setser_dec_15_17#Q` (question) 'Why does the U.S. trade balance still matter,\neven if defici'
- `setser_feb_15_18#Q` (question) "Will Trump's fiscal expansion undermine\nhis goal of reducing"
- `setser_jun_4_18#Q` (question) 'Could global macro shocks overwhelm trade deals\nand push the'
- `setser_may_2_19#Q` (question) 'If U.S.-China trade tensions escalate,\nwill China keep the y'
- `setser_may_10_19#Q` (question) 'If U.S.-China trade tensions escalate,\nwill China keep the y'
- `setser_jun_14_19#Q` (question) "Why did China's tariffs devastate some U.S. exports\nbut have"
- `setser_aug_13_19#Q` (question) 'Why do the U.S., Europe, and China now occupy\nsuch different'
- `setser_sep_20_19#Q` (question) 'Why do global trade imbalances persist,\nand why could they w'
- `setser_jan_31_20#Q` (question) 'How did China choose to respond to tariff pressure, and what'
- `setser_feb_26_20#Q` (question) 'Do tariffs change the trade balance,\nand who absorbed the Q4'
- `setser_mar_31_20#Q` (question) 'Emerging economies face the same shocks — do they need the s'
- `setser_jul_8_20#Q` (question) 'Is China on track to meet its Phase One purchase commitments'
- `setser_mar_10_24#Q` (question) "Is China's centrality to global manufacturing really declini"
- `setser_aug_14_24#Q` (question) 'Why does the reported current account diverge from the custo'
- `setser_2025-07-07_china-stealth-surplus#Q` (question) "Why does China's surplus look small in IMF imbalance data wh"
- `setser_2025-07-28_china-eu-trade-war#Q` (question) 'Why is Europe losing ground to China in trade, and what shou'
- `setser_2025-09-12_trump-shock-that-wasnt#Q` (question) "Have Trump's tariffs actually shocked trade flows and the gl"
- `setser_2025-11-12_china-surplus-imf#Q` (question) "How big is China's surplus really, why does the IMF miss it,"
- `setser_2026-02-03_october-2025-deficit#Q` (question) 'Does the low October 2025 trade deficit mean the tariffs are'

## Flagged for review

## unresolved counterpoint (9)

- `setser_feb_15_18` - R1 'Offsetting adjustment forces' - stays generic `counterpoint`
- `setser_feb_26_20` - X 'Consensus: tariffs move level, not balance' - stays generic `counterpoint`
- `setser_feb_26_20` - QF 'COVID confound' - stays generic `counterpoint`
- `setser_feb_26_20` - R1 'Rival causes of weak capex' - stays generic `counterpoint`
- `setser_jun_14_19` - R1 'Auto counterfactual' - stays generic `counterpoint`
- `setser_jun_4_18` - R1 'Offsetting scenario' - stays generic `counterpoint`
- `setser_may_10_19` - X 'Case for stability' - stays generic `counterpoint`
- `setser_may_2_19` - X 'Case for stability' - stays generic `counterpoint`
- `setser_sep_20_19` - R1 'Japan exception' - stays generic `counterpoint`

Fix by adding the term to `scripts/schema_map.yaml` and re-running.

## Normalized node types

-   65 evidence_data
-   59 mechanism
-   43 stated_assumption
-   42 intermediate_claim
-   29 caveat
-   21 main_claim
-   20 question
-   13 opposing_view
-   12 hidden_assumption
-   11 other_explanation
-   11 evidence_source
-    9 counterpoint
-    3 revised_prior
-    3 source_credibility
-    3 recommendation
-    2 scope_choice
-    2 evidence_discrepancy
-    2 deferred_question
-    1 case_type
-    1 benchmark
-    1 accounting_identity
-    1 policy_reductio
-    1 evidence_rival
-    1 reconstruction
-    1 anomaly
-    1 position_map

## Normalized edge types

-  246 supports
-   31 qualified_by
-   21 undercut_by
-   17 licenses
-   12 rebuts
-    4 motivates
-    3 revises
-    3 bounds
-    2 defers
-    1 reconstructs
