# AIF conformance

- I-nodes: 359
- RA-nodes (inference): 388
- CA-nodes (conflict): 67
- edges: 910 (every argument relation reified as I -> S -> I)

## Core constraints

- no I-node links directly to another I-node: PASS
- every S-node sits between two I-nodes: PASS
- role hierarchy rolls up (each oper family has one Toulmin parent): PASS
- every relation has an AIF S-node kind: PASS

## Toulmin coverage

| element | claims |
|---|---|
| warrant | 115 |
| grounds | 80 |
| claim | 69 |
| rebuttal | 35 |
| qualifier | 29 |
| framing | 23 |
| backing | 4 |
| revision | 3 |
| unassigned | 1 |

**332 of 359 claims (92%) occupy a Toulmin element.** The remaining 27 are `framing` (article-level apparatus - AIF+ dialogue territory), `revision` (a change of mind across articles, which neither Toulmin nor AIF can hold) and `unassigned`. That residue is the part of this model that is genuinely ours, and it is recorded rather than forced into a slot it does not fit.

