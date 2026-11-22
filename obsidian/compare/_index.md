---
type: index
tags: [canvas, compare]
---

# Hand-drawn vs model maps

One canvas per article that has both a hand-drawn map and an official model run. The hand map is on the left and the model's map on the right, laid out by level, with the same card on both sides: ID, role, cited paragraphs (¶), the claim, and the hand map's gloss or the model's "why".

Cyan edges are the pairs found by the annotation pipeline's box matcher (`annotation/src/annotate/evaluate.py`), the same pairs as that run's `evaluation.md`. `paragraph` means the two steps cite a common paragraph; `slot` means only the role matched. Unmatched cards sit on the outside of each row.

The hand map is one person's reading, not a gold standard.

| canvas | hand steps | model steps | matched | by paragraph |
|---|---|---|---|---|
| [[2017-12-15 Why does the U.S. trade balance still matter, even if deficits can accompany strong (hand vs model).canvas\|2017-12-15 Why does the U.S. trade balance still matter, even if deficits can accompany strong (hand vs model)]] | 21 | 26 | 11 | 9 |
| [[2019-05-10 If U.S.-China trade tensions escalate, will China keep the yuan stable or let it weaken (hand vs model).canvas\|2019-05-10 If U.S.-China trade tensions escalate, will China keep the yuan stable or let it weaken (hand vs model)]] | 23 | 25 | 8 | 7 |
| [[2019-06-14 Why did China's tariffs devastate some U.S. exports but have limited effects on others (hand vs model).canvas\|2019-06-14 Why did China's tariffs devastate some U.S. exports but have limited effects on others (hand vs model)]] | 22 | 24 | 10 | 10 |
| [[2019-09-20 Why do global trade imbalances persist, and why could they worsen before improving (hand vs model).canvas\|2019-09-20 Why do global trade imbalances persist, and why could they worsen before improving (hand vs model)]] | 24 | 27 | 9 | 8 |
| [[2020-01-31 Lessons From Phase One of the Trade War With China (hand vs model).canvas\|2020-01-31 Lessons From Phase One of the Trade War With China (hand vs model)]] | 14 | 25 | 12 | 9 |
| [[2020-03-31 Not One Emerging Market Financial Crisis, but Many (hand vs model).canvas\|2020-03-31 Not One Emerging Market Financial Crisis, but Many (hand vs model)]] | 14 | 27 | 11 | 8 |
| [[2024-08-14 China's Imaginary Trade Data (hand vs model).canvas\|2024-08-14 China's Imaginary Trade Data (hand vs model)]] | 17 | 22 | 14 | 11 |
| [[2025-09-12 The Trump Shock That Wasn't (At Least Not Yet) (hand vs model).canvas\|2025-09-12 The Trump Shock That Wasn't (At Least Not Yet) (hand vs model)]] | 15 | 24 | 10 | 8 |
| [[2025-11-12 China's Massive Surplus is Everywhere (Yet The IMF Still Has Trouble Seeing It Clearly) (hand vs model).canvas\|2025-11-12 China's Massive Surplus is Everywhere (Yet The IMF Still Has Trouble Seeing It Clearly) (hand vs model)]] | 14 | 23 | 9 | 5 |
| [[2026-02-03 Understanding the Low October 2025 Trade Deficit (hand vs model).canvas\|2026-02-03 Understanding the Low October 2025 Trade Deficit (hand vs model)]] | 15 | 19 | 10 | 7 |

Back to [[index]].
