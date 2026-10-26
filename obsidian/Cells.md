---
type: reference
tags: [reference]
---
# Cells

Every claim is filed on two independent axes: **role** is what it does in an
argument, **subject** is what it is about. Neither is a sub-category of the
other, so crossing them asks a question neither axis can be asked alone - and
nothing in any map is tagged with the answer.

Needs the **Dataview** plugin. If a block shows as plain text, reload Obsidian
(`Ctrl+R`) - Dataview only loads at startup.

> Hand-written, and the export does not touch it. `index.md`, `claims/`,
> `articles/`, `concepts/`, `subjects/` and `views/` are all regenerated, so
> anything added there is lost on the next run.

## What he assumes and never defends

The unstated warrants - what the argument needs and the article never says - **13 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, date, article
FROM #type/hidden_assumption
SORT date ASC
```

## What he assumes about China

```dataview
TABLE WITHOUT ID file.link AS Claim, date, article
FROM #type/hidden_assumption
WHERE contains(country_subject, "china")
SORT date ASC
```

## What he assumes about the US

```dataview
TABLE WITHOUT ID file.link AS Claim, date, article
FROM #type/hidden_assumption
WHERE contains(country_subject, "us")
SORT date ASC
```

## What he assumes when a claim is about a pair

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM (#type/hidden_assumption OR #type/stated_assumption OR #type/accounting_identity) AND #shape/bilateral
SORT date ASC
```

## What he concedes on tariffs

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM (#type/caveat OR #type/opposing_view OR #type/counterpoint OR #type/other_explanation) AND #instrument/tariffs
SORT date ASC
```

## What he concedes about China

Every caveat, counterpoint, rival explanation and opposing view with China as subject - **22 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM (#type/caveat OR #type/opposing_view OR #type/counterpoint OR #type/other_explanation)
WHERE contains(country_subject, "china")
SORT date ASC
```

## Mechanisms he reaches for on the current account

Causal channels, one variable - **10 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, date, article
FROM #type/mechanism AND #variable/current-account
SORT date ASC
```

## Mechanisms on the exchange rate

The same cut, a different variable - **10 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, date, article
FROM #type/mechanism AND #variable/nominal-exchange-rate
SORT date ASC
```

## China under tariffs

Both subject facets, no role filter - the whole argument on one topic pair - **10 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM #instrument/tariffs
WHERE contains(country_subject, "china")
SORT date ASC
```

## What rests on customs data

His preferred evidence base - he argues *from* customs data - **41 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM #data_basis/customs
SORT date ASC
```

## What rests on balance-of-payments data

The base he argues *about* - the discrepancy claims live here - **31 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM #data_basis/balance-of-payments
SORT date ASC
```

## Where the data itself is the problem

Claims whose content is a discrepancy, or a reason to distrust a source - **5 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM (#type/evidence_discrepancy OR #type/source_credibility)
SORT date ASC
```

## What he has changed his mind about

The role axis has a revision level; this is all of it - **3 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, date, article
FROM #type/revised_prior
SORT date ASC
```

## Bilateral trade flows, every role

One variable across the whole argument - sort by role to see the shape - **28 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM #variable/bilateral-trade-flows
SORT date ASC
```

## Scope choices and benchmarks

How he bounds a question before answering it, and what he measures against - **3 claims**.

```dataview
TABLE WITHOUT ID file.link AS Claim, type, date, article
FROM (#type/scope_choice OR #type/benchmark)
SORT date ASC
```

---

## Writing your own

Tag namespaces, all present on every claim note:

| namespace | values | what it is |
|---|---|---|
| `#type/` | 26 | the role, e.g. `hidden_assumption`, `mechanism`, `caveat` |
| `#level/` | L0-L6 | the stage of the argument it was drawn in |
| `#variable/` | 34 | the economic quantity it is about |
| `#instrument/` | 13 | the policy lever |
| `#data_basis/` | 11 | the evidence base it rests on |
| `#where/` | 15 | country or bloc - **either role**, see the caution below |
| `#shape/bilateral` | - | a counterpart is set: 90 claims, 14 ordered pairs |
| `#family/` | 3 | which annotation template the article used |

`FROM #a AND #b` is the cross; `FROM #a AND (#b OR #c)` widens one side.
`WHERE date > date(2024-01-01)` cuts by period - but that is the article's
publication date, not the period the claim is *about*.

## Three cautions

**`#where/` is not "about".** It carries both roles, so `#where/china` also
returns claims about *another* economy that merely have China on the other
side - one of the 8 hidden assumptions it matches is about the euro area. When
you mean "about", filter the field instead:

```
WHERE contains(country_subject, "china")
```

That is the difference between 8 and 7 on the first China cell, and it is why
the queries above use the field rather than the tag.

**A strict AND over leaf terms goes empty fast.** Two facets leave 21% of all
bindings non-empty; three facets, 1.8%. If a cell returns nothing, widen one
side with an OR rather than concluding he never wrote about it.

**`us` and `china` are saturated** - 53% and 50% of all claims, which is why
both carry `#subject/saturated`. Crossing them with a role is the useful move;
using either alone as a filter is not.

