# Parse review

20 documents -> 359 nodes, 455 edges.

## Defaults applied - these are conventions, not authored decisions

- **294 of 455 edges carry no label** in the source and took `edge_default_solid` (`supports`). An unlabelled solid arrow meaning support is the drawing convention across all 20 maps, but it is still a default: only 161 edges state their type explicitly.
- Node types resolved by: 188 from class, 148 from header, 23 from l6_keyword. A type resolved by `level` alone is the weakest inference - see the `type_source` column in nodes.csv.

## Nodes in no edge (5)

Mostly Level 0 question nodes: the schema says L0 `==>|frames|` L1, but every article map draws that link with `~~~`, which is layout-only and carries no meaning. The question is therefore not connected to the argument it frames. Worth a schema decision rather than a parser fix.

- `setser_jan_31_20#Q` (question) 'How did China choose to respond to tariff pressure, and what'
- `setser_mar_31_20#Q` (question) 'Emerging economies face the same shocks — do they need the s'
- `setser_jul_8_20#Q` (question) 'Is China on track to meet its Phase One purchase commitments'
- `setser_mar_10_24#Q` (question) "Is China's centrality to global manufacturing really declini"
- `setser_aug_14_24#Q` (question) 'Why does the reported current account diverge from the custo'

## Flagged for review

## layout edges with no evidence to derive from (1)

- `corpus` - 108 edges typed `frames` by declared convention. These role pairs carry NO labelled example anywhere, because the annotator used the unlabelled `~~~` operator for exactly this structure - so there is nothing to back off to. Sign 0: the structure is recorded without asserting support we cannot evidence.

## unresolved counterpoint (8)

- `setser_feb_15_18` - R1 'Offsetting adjustment forces' - stays generic `counterpoint`
- `setser_feb_26_20` - X 'Consensus: tariffs move level, not balance' - stays generic `counterpoint`
- `setser_feb_26_20` - QF 'COVID confound' - stays generic `counterpoint`
- `setser_feb_26_20` - R1 'Rival causes of weak capex' - stays generic `counterpoint`
- `setser_jun_14_19` - R1 'Auto counterfactual' - stays generic `counterpoint`
- `setser_jun_4_18` - R1 'Offsetting scenario' - stays generic `counterpoint`
- `setser_may_10_19` - X 'Case for stability' - stays generic `counterpoint`
- `setser_sep_20_19` - R1 'Japan exception' - stays generic `counterpoint`

Fix by adding the term to `scripts/schema_map.yaml` and re-running.

## Normalized node types

-   66 evidence_data
-   59 mechanism
-   42 stated_assumption
-   42 intermediate_claim
-   27 caveat
-   21 main_claim
-   20 question
-   15 opposing_view
-   13 hidden_assumption
-   12 other_explanation
-   11 evidence_source
-    8 counterpoint
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

-  248 supports
-  108 frames
-   29 qualified_by
-   21 undercut_by
-   21 licenses
-   14 rebuts
-    4 motivates
-    3 defers
-    3 revises
-    3 bounds
-    1 reconstructs
