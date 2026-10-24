# Argument maps

359 claims across 20 articles.

Open the graph view (Ctrl/Cmd+G) and click any claim to expand it. Use the local-graph pane to follow one argument at a time.

Every claim is filed on two independent axes. **Role** is what a claim does in an argument; **subject** is what it is about. Neither is a sub-category of the other, which is why there are two sets of views rather than one tree.

## Browse by role — what a claim does

- [[Assumptions]] — 65
- [[Evidence]] — 80
- [[Mechanisms]] — 59
- [[Conclusions]] — 25
- [[Counterpoints]] — 64
- [[Questions]] — 22
- [[Intermediate steps]] — 44

## Browse by subject — what a claim is about

- [[By variable]] — 34 terms, 359 claims
- [[By country]] — 11 terms, 329 claims
- [[By bloc]] — 7 terms, 39 claims
- [[By instrument]] — 13 terms, 180 claims
- [[By data basis]] — 11 terms, 109 claims
- [[Bilateral]] — 90 claims across 14 country pairs

Cross the two axes to answer a question on one topic without reading the whole corpus. In the graph filter box:

- `tag:#variable/current-account tag:#type/hidden_assumption` — the unstated warrants behind his current-account arguments
- `tag:#shape/bilateral tag:#type/stated_assumption` — what he assumes when the claim is bilateral
- `tag:#data_basis/balance-of-payments` — every claim resting on BoP data, including the critiques of it
- `tag:#where/china tag:#instrument/tariffs` — China under tariffs

**[[Cells]]** holds these as ready Dataview tables, one per cell, with its row count — and uses `country_subject` rather than `#where/`, which carries the counterpart role too. That note is hand-written and this export does not touch it.

The role cuts still work the same way:

- `tag:#type/hidden_assumption` — just the unstated warrants
- `path:claims/mechanism` — just the causal channels
- `tag:#level/L1` — everything at the assumptions level
- `tag:#family/meta` — only the 2025+ template

## By type

- `evidence_data` — 66
- `mechanism` — 59
- `stated_assumption` — 42
- `intermediate_claim` — 42
- `caveat` — 27
- `main_claim` — 21
- `question` — 20
- `opposing_view` — 15
- `hidden_assumption` — 13
- `other_explanation` — 12
- `evidence_source` — 11
- `counterpoint` — 8
- `revised_prior` — 3
- `source_credibility` — 3
- `recommendation` — 3
- `scope_choice` — 2
- `evidence_discrepancy` — 2
- `deferred_question` — 2
- `case_type` — 1
- `benchmark` — 1
- `accounting_identity` — 1
- `policy_reductio` — 1
- `evidence_rival` — 1
- `reconstruction` — 1
- `anomaly` — 1
- `position_map` — 1

## Articles

- 2017-12-15 [[2017-12-15 Why does the U.S. trade balance still matter, even if deficits can accompany strong growth]] `plain`
- 2018-02-15 [[2018-02-15 Will Trump's fiscal expansion undermine his goal of reducing the U.S. trade deficit]] `plain`
- 2018-06-04 [[2018-06-04 Could global macro shocks overwhelm trade deals and push the U.S. trade deficit higher]] `plain`
- 2019-05-02 [[2019-05-02 Does a purchase-commitment deal push China back toward managed trade]] `plain`
- 2019-05-10 [[2019-05-10 If U.S.-China trade tensions escalate, will China keep the yuan stable or let it weaken]] `plain`
- 2019-06-14 [[2019-06-14 Why did China's tariffs devastate some U.S. exports but have limited effects on others]] `plain`
- 2019-08-13 [[2019-08-13 Why do the U.S., Europe, and China now occupy such different positions in manufacturing trade]] `plain`
- 2019-09-20 [[2019-09-20 Why do global trade imbalances persist, and why could they worsen before improving]] `plain`
- 2020-01-31 [[2020-01-31 Lessons From Phase One of the Trade War With China]] `banner`
- 2020-02-26 [[2020-02-26 Do tariffs change the trade balance, and who absorbed the Q4 US demand drop]] `plain`
- 2020-03-31 [[2020-03-31 Not One Emerging Market Financial Crisis, but Many]] `banner`
- 2020-07-08 [[2020-07-08 Slouching Toward Phase One]] `banner`
- 2024-03-10 [[2024-03-10 China's Record Manufacturing Surplus]] `banner`
- 2024-08-14 [[2024-08-14 China's Imaginary Trade Data]] `banner`
- 2025-05-05 [[2025-05-05 Why Didn't Tariffs Push Up the U.S. Dollar]] `banner`
- 2025-07-07 [[2025-07-07 China's Stealth Trade Surplus]] `meta`
- 2025-07-28 [[2025-07-28 China is also Fighting a Trade War with Europe (and Winning)]] `meta`
- 2025-09-12 [[2025-09-12 The Trump Shock That Wasn't (At Least Not Yet)]] `meta`
- 2025-11-12 [[2025-11-12 China's Massive Surplus is Everywhere (Yet The IMF Still Has Trouble Seeing It Clearly)]] `meta`
- 2026-02-03 [[2026-02-03 Understanding the Low October 2025 Trade Deficit]] `meta`

## Concepts (what links articles together)

- [[bop-understates-china-surplus]] — 2 articles
- [[debt-dynamics-sensitive-to-rates]] — 2 articles
- [[deficits-require-financing]] — 2 articles
- [[state-can-direct-purchases]] — 3 articles

## Dataview queries (optional plugin)

The hub and view notes list their claims directly, so none of this is required. With the Dataview plugin installed, these return the same sets as sortable tables — and [[Cells]] has a larger set, kept by hand:

````
```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM #variable/bilateral-trade-flows
SORT date ASC
```

```dataview
TABLE WITHOUT ID file.link AS Claim, article
FROM #shape/bilateral AND (#type/stated_assumption OR #type/hidden_assumption)
SORT date ASC
```

```dataview
TABLE WITHOUT ID file.link AS Claim, type, variable
FROM #where/china AND #instrument/tariffs
SORT date ASC
```
````


## Notes

- **For an ordered, hierarchical view, use [[_index|the canvases]]** — one per article, laid out by argument level. Obsidian's graph is force-directed and cannot draw a hierarchy; a canvas can.
- In the graph view, the useful filters, measured on this vault at export time (476 notes, 3317 links between them, mean degree 13.9):
    - `-path:subjects -path:views -file:index` → 386 notes, 856 links, mean degree **4.4** — the per-article argument trees, joined only where a concept spans articles
    - `-path:subjects -path:views -path:canvas -path:articles -file:index` → **the argument only**: 366 notes, 468 links, mean degree 2.6, busiest node 9. Dropping the article notes matters more than it sounds — removing them takes 388 of the 856 links with them, nearly all of it membership rather than reasoning, and each article note is a star at the centre of its cluster that the force layout bends everything around. Turn on Display → Arrows here: the direction is the content.
    - `-path:canvas` → the canvases are files too and every card on one counts as a link, so they add 359 link-ends to the graph view. They are for reading, not for the force layout.
    - `-tag:#subject/saturated` → drops just `china`, `us`, which carry 476 of the 3317 link-ends between them, and keeps the other 74 hubs
- Every link shows its sign: **+1** backs, **-1** pushes back, **0** neither. The sign is argumentative, not causal - it means *backs* and *pushes back on*, never *increases* and *decreases*.
- Each link records how its relation was known, in frontmatter: `label` (the annotator wrote it), `arrow` (from the arrow style, by convention) or `layout_operator` (recovered from the map's `~~~` links, which carry the question-to-priors and prior-to-evidence structure).
- Articles use three annotation templates (`plain`, `banner`, `meta`); the `family` tag on every note records which.
