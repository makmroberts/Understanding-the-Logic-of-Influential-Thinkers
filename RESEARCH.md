# Ontology and knowledge-graph methods: research notes

Methods research, Oct 2026. Findings and sources; conclusions left open.
◍ = read at abstract level only. References at the end, checked against each
paper's own page.

---

## 1. Where ontology learning works, and where it doesn't

The field splits the problem into term extraction, term typing, taxonomy
discovery, non-taxonomic relation extraction, and axiom discovery. Reported
performance is uneven:

| Task | Reported |
|---|---|
| Term typing | F1 ≈ 0.92 |
| Taxonomy discovery | F1 ≈ 0.854 |
| Non-taxonomic relation extraction | weak |
| Axiom discovery | weak |

- Mishra et al. (2026) ◍ report both figures above and extracted **no**
  non-taxonomic relations. They describe LLMs as tending to "favor hierarchical
  over associative relations."
- SPIRES (Caufield et al. 2024) grounds entity *names* to ontology identifiers at
  97–100%, but reaches only F ≈ 0.41–0.44 on relation extraction (precision
  0.43–0.69, recall 0.26–0.39), using no training data.

Our 455 links (`backs`, `pushes back on`, `frames`) are non-taxonomic, and
argumentative rather than factual — a claim's function in an argument, not a
relation in the world.

---

## 2. Tools

| Tool | What it does | Caveat for us |
|---|---|---|
| **OntoLearner** ([repo](https://github.com/sciknoworg/OntoLearner), MIT) | 150+ ontologies over 23 domains; the four learning tasks; `evaluation_report` scores predictions against ground truth | Outputs *ontologies*, not instance data — it doesn't draw maps. Its finance domain is one ontology (GoodRelations, e-commerce, last updated Oct 2011, 98 classes); there is no economics domain |
| **SPIRES / OntoGPT** ([repo](https://github.com/monarch-initiative/ontogpt)) | Walks a schema recursively, one class per prompt; asks for entity *names*, grounds them against the ontology, validates every identifier | A run without the grounding step returned 3 correct identifiers out of 100 |
| **Text2KGBench** ([repo](https://github.com/cenguix/Text2KGBench)) | Benchmark for ontology-driven KG generation; 7 metrics | Two of its metrics name things we already enforce: *ontology conformance* and *faithfulness* |
| **LinkML** ([repo](https://github.com/linkml/linkml), Apache-2.0) | Schema language, YAML-authored, 30+ generators (JSON Schema, Pydantic, SQL DDL, OWL, SHACL, SPARQL) | No property-graph binding — a Cypher target stays hand-written |

### Triage: where each tool acts

Placed by what each one needs as *input*. The bottleneck is **map authoring** —
instance-level, argumentative relations — and almost nothing in the inventory
reaches it.

| Tool | Needs as input | Stage it acts at | On the critical path? |
|---|---|---|---|
| **SPIRES / OntoGPT** | a schema + text | **map authoring** | **yes** — the one real hit |
| **RELRaE** ◍ | text | **map authoring** | unverified (abstract only) |
| OntoRAG, OMD-GraphRAG | raw PDFs | end-to-end; induces the ontology | no — implements the design §2.2 rejected |
| Helix Foundry | records (Postgres, S3, Slack, Notion …) | end-to-end; agent drafts the schema | no — input is records, not prose |
| EvoOntology | a data workload + agent traces | vocabulary evolution | no — no text→argument step; governance pattern only |
| OntoLearner | an ontology + ground truth | evaluation | cheap to adopt; creates no corpus |
| Text2KGBench | a built KG + ontology | evaluation | metric vocabulary only |
| LinkML, SHACL / pySHACL | a schema; a graph + shapes | schema→targets; validation | portability work, do now |
| Neo4j, TerminusDB, Kuzu, Aura | a built graph | store | deferred by design — the store is a view |
| OLaLa, LLMs4OM, GenOM, OAEI-LLM | **two** ontologies | alignment | refused — one shared vocabulary, nothing to align |
| Foundry, OpenFoundry, OntoForge | a built ontology | platform | export target only |

Two of roughly fifteen act where the work is, and the better-documented one
reports F ≈ 0.41–0.44 on relations against 97–100% on grounding. The field's
toolchain presupposes the instance data, because the field's task is term typing
and taxonomy. That absence is corpus-side support for the contribution claim,
and it means map automation is **build, not adopt** — though the thing to build
is a second instance of the `label_facets.py` contract (runtime schema whose
enums are the vocabulary, validate-and-trim, provenance column, report rather
than invent), one layer up.

**The counterfactual, stated.** Helix Foundry and OntoRAG both have AI draft the
ontology for a human to review — the inverse of the division of labour settled on
CQ4OE grounds. The defence is **checkability**, not the citation: their drafted
types sit over records with external referents, so a bad type breaks a query
visibly. Argumentative roles have no referent outside the text — the corpus *is*
the evidence — so a bad role has nothing to be caught by. Tested directly by the
Create arm in `KoL Reasoning - Map Automation Experiment` (vault).

**Spot-check still owed on Helix** before citing it: commit history, and whether
the ontology agent is implemented or a stub. The three repos checked in §7 were
polished READMEs ahead of implementation; HelixDB being a real company makes it
more credible, not checked.

---

## 3. Three findings on method

**Assignment beats construction.** Li, Wang, Garijo & Poveda-Villalón (2026) ◍
score nine LLMs over 99 term-level and 118 ontology-level competency questions:
models "recover explicit vocabulary terms more reliably than creating
ontologies," with the gap in property modelling, hierarchy and axioms.

**Scale doesn't help.** Babaei Giglou, Auer & D'Souza (2026) ◍ sweep model sizes
over ~3 orders of magnitude on ontology learning: gains plateau, small models
often match large.

**Planning beats repair.** Talukder, Mridul & Seneviratne (2026) ◍ compare
single- and multi-agent ontology generation on insurance contracts and attribute
most of the multi-agent gain to front-loaded planning, not iterative repair.

---

## 4. Vocabulary reuse: STW mapping test

Context: the README notes `facets.yaml` was written while reading the same twenty
articles it labels, so its consistency score measures internal consistency only.

**SDMX** (Statistical Data and Metadata eXchange) **and the W3C RDF Data Cube
don't apply** — both standardise *structural* metadata: frequency, reference
area, reference period, adjustment, unit of measure. Neither publishes a list of
economic variables. Useful for country codes and indicator-series metadata.

**STW Thesaurus for Economics** (*Standard-Thesaurus Wirtschaft*, published by
the ZBW, Germany's national library of economics) — 6,000+ economics subject
headings, 20,000+ synonyms, in SKOS, already mapped to the *Journal of Economic
Literature* codes, Wikidata, DBpedia, EuroVoc and the SDMX subject domains.

**Method.** All 77 facet terms queried against the STW API: first as written
(kebab-case expanded), then against hand-written alternative phrasings.
Grades: `exact` (preferred-label match), `alt` (published synonym), `partial`
(hit only after dropping qualifiers), `none`.

| Facet | n | exact | alt | partial | none |
|---|---|---|---|---|---|
| `variable` | 34 | 22 | 5 | 3 | 4 |
| `country` | 12 | 12 | 0 | 0 | 0 |
| `instrument` | 13 | 10 | 2 | 1 | 0 |
| `bloc` | 7 | 2 | 1 | 1 | 3 |
| `data_basis` | 11 | 6 | 0 | 2 | 3 |
| **total** | **77** | **52** | **8** | **7** | **10** |

Of the 60 exact-or-synonym hits, **25 matched the term as written**; **35 needed
one of the hand-written phrasings**, so the alias list is part of the result.
Questionable ones on inspection: `swap-lines` → a currency-derivative
descriptor, `retaliation` → a broad foreign-economic-policy heading,
`fiscal-impulse` → fiscal policy, `manufacturing-employment` → employment.

**Terms that collapse.** Three cases where two facet terms resolve to one
descriptor:

| Facet terms | STW descriptor |
|---|---|
| `goods-trade-balance`, `manufacturing-trade-balance` | trade balance |
| `national-saving`, `savings-investment-gap` | savings |
| `customs`, `mirror-statistics` | foreign trade statistics |

Mirror statistics — comparing two countries' reported figures for the same flow —
has no STW term, and appears in several China-surplus articles.

**`data_basis`.** Its matches are largely spurious: `academic-econometrics` → the
discipline, `press-reporting` → press distribution, `imf-publications` →
conditionality. The facet classifies what *evidence* a claim rests on, not what
it's about. One consequence: the independence statistic in `PROCESS.md` crosses
role against the subject facets with `data_basis` among them, so it is role ×
(subject + basis) combined rather than role × subject.

---

## 5. Operational ontology primitives

Palantir's documentation separates semantic elements (object types, properties,
link types, interfaces) from kinetic ones (action types, functions, security).
Their stated rationale: an ontology "represents the *decisions* in an
enterprise, not simply the data," because conventional architectures record
neither the reasoning behind a decision nor the actions that followed.

- **Interfaces** — a shape an object type must expose, with several types
  implementing it differently. Compare Markóczy & Goldberg's (1995) fixed
  construct pool, which standardises the construct vocabulary across respondents
  so maps can be compared.
- **Action types** — validated, audited writes: several edits committed together,
  with submission rules that must pass before anything lands.

No description-logic reasoner is involved; reasoning sits in application code.

---

## 6. From our own data: passage anchoring by role

| Role | n | anchored | % |
|---|---|---|---|
| `evidence_source` | 11 | 8 | 72.7 |
| `evidence_data` | 66 | 32 | 48.5 |
| `other_explanation` | 12 | 3 | 25.0 |
| `opposing_view` | 15 | 3 | 20.0 |
| `mechanism` | 59 | 8 | 13.6 |
| `caveat` | 27 | 2 | 7.4 |
| `main_claim` | 21 | 1 | 4.8 |
| `stated_assumption` | 42 | 1 | 2.4 |
| `intermediate_claim` | 42 | 1 | 2.4 |
| `question` | 20 | 0 | 0.0 |
| `hidden_assumption` | 13 | 0 | 0.0 |
| `counterpoint` | 8 | 0 | 0.0 |

`hidden_assumption` is 13 of 359 claims (3.6%), none anchored. `PROCESS.md`
already notes that "is this the source?" has no yes/no answer for an unstated
assumption — but the grading records those as `candidate` or no-passage, the
same values used when a passage search simply failed.

---

## 7. Stack notes

Relevant because `docker-compose.yml` pins `neo4j:5-community`, and because the
§5 primitives are Foundry features rather than open-source ones.

**Neo4j constraints are mostly Enterprise.** Of the four constraint types in the
[Cypher manual](https://neo4j.com/docs/cypher-manual/current/constraints/managing-constraints/),
only property uniqueness is in Community Edition; property existence, property
type and key constraints are Enterprise-only.
[`GRAPH TYPE`](https://neo4j.com/blog/developer/graph-type-schema-enforcement-made-easy-preview/)
(schema declaration, GA v2026.06) is documented for Enterprise, Infinigraph and
all Aura tiers — Community is not listed.

**AuraDB Free** ([quotas](https://neo4j.com/docs/aura/quotas-and-limits/)) —
200,000 nodes / 400,000 relationships (our corpus: 359 claims, 455 edges);
paused after 3 days without a write, deleted 30 days after pausing. Whether Free
carries the Enterprise constraint types isn't stated in the quotas docs —
untested.

**Kuzu is archived.** Embedded, schema-first, every relationship table declaring
permitted endpoints — a good technical fit, but the
[repo](https://github.com/kuzudb/kuzu) was archived 10 Oct 2025 (final release
0.11.3, MIT, 4.0k stars) after Apple acquired Kùzu Inc. Two maintained forks:
[LadybugDB](https://github.com/LadybugDB/ladybug), run by Arun Sharma
(previously Facebook's Dragon graph query system), reporting 20+ releases,
1,000+ commits and 80+ contributors by Nov 2025; and
[Vela-Engineering/kuzu](https://github.com/Vela-Engineering/kuzu), which adds
concurrent multi-writer support for agent memory.

**TerminusDB** ([repo](https://github.com/terminusdb/terminusdb)) — knowledge
graph store with version control: time-travel, branch, merge, diff,
schema-enforced documents, each change an immutable delta. Apache-2.0, 3.5k
stars, actively developed; release 12.0.7 at time of checking.

**"Open-source Foundry" projects.** Several exist and are promoted actively.
Maturity and adoption vary a lot; three checked:

| Repo | Stars | Forks | Commits | State |
|---|---|---|---|---|
| [`cloudbadal007/foundry-ontology-open`](https://github.com/cloudbadal007/foundry-ontology-open) | 107 | 30 | 2 | detailed README advertising an OWL/SHACL export bridge |
| [`smilebank7/OpenFoundry`](https://github.com/smilebank7/OpenFoundry) | 4 | 3 | 1 | self-described "Phase 0 — Infrastructure Skeleton"; the ontology layer is unimplemented |
| [`jachenms/OntoForge`](https://github.com/jachenms/OntoForge) | 2 | 0 | 24 | working code — HTML workbench, zero-dependency Python package, CI and ~100 test assertions |

Others in the cluster, unchecked: OpenFoundry under at least three further
owners, Helix Foundry, [Scrydon](https://scrydon.com/).

**Validation without action types.** SHACL (Shapes Constraint Language) is the
[W3C language](https://www.w3.org/TR/shacl/) for validating RDF graphs against
declared constraints — the nearest open standard to an action type's pre-commit
check. Implementations: [pySHACL](https://github.com/RDFLib/pySHACL)
(Apache-2.0) and [Apache Jena SHACL](https://jena.apache.org/documentation/shacl/)
(Apache-2.0), which covers SHACL Core and SHACL SPARQL Constraints.

**Portability.** ISO/IEC 39075:2024 (GQL, the property-graph query standard)
published Apr 2024; corrigendum 2026, second edition in development. Portable
across compliant stores: `MATCH`, `CREATE`, `MERGE`, `WHERE`, `RETURN`, `WITH`,
`UNWIND`, patterns, parameters, expressions. Not portable: procedures (e.g.
Neo4j's APOC library), index and admin commands, vendor extensions.
`export_neo4j.py` already avoids APOC and file mounting. PG-Schema (Angles et al.
2023) proposes property-graph types with multi-inheritance to inform GQL's second
edition; no known implementation.

**Foundry access.** Palantir runs a free AIP Developer Tier at
build.palantir.com for individuals in supported countries, capacity-capped. As of
late Oct 2026 signups are paused, waitlist only.

---

## 8. Open questions

- Inter-annotator agreement: the Krippendorff's alpha implementation is listed in
  `PROCESS.md` as validated with nothing to measure. Three annotators, no
  overlapping articles. Separate figures for roles, links and
  `hidden_assumption` would each mean something different.
- Annotator effects are testable without new annotation — role-mix and
  link-density distributions compared across annotators.
- Model-drawn maps vs hand-drawn, scored on conformance and faithfulness
  separately.
- The independence statistic has no implementation in `scripts/`; with 661
  assignments over an 11 × 34 table, its power against a known moderate
  association is unmeasured.
- Term accumulation: new facet terms per article in annotation order, and the
  second-thinker vocabulary delta.
- STW mapping policy per term — adopt, map, or keep with a recorded reason.
- Passage review queue: 0 of 270 reviewed (140 `clear`, 46 `moderate`, 84 `tie`).
- Whether AuraDB Free accepts the Enterprise constraint types — a ten-minute
  test that decides whether free database-level schema enforcement exists.

---

## References

**Ontology learning**

- Babaei Giglou, H., D'Souza, J. & Auer, S. (2023). *LLMs4OL: Large Language Models for Ontology Learning.* ISWC 2023 research track. https://arxiv.org/abs/2307.16648
- Babaei Giglou, H., Auer, S. & D'Souza, J. (2026). *When Does Bigger Help? A Controlled Study of LLM Scale for Ontology Learning.* https://arxiv.org/abs/2608.31118
- Babaei Giglou, H., D'Souza, J., Aioanei, A., Mihindukulasooriya, N. & Auer, S. (2026). *OntoLearner: A Modular Python Library for Ontology Learning with Large Language Models.* Preprint, under review. https://arxiv.org/abs/2607.01977 · https://github.com/sciknoworg/OntoLearner · https://huggingface.co/datasets/SciKnowOrg/ontolearner-finance
- Mishra, S., Meena, D. R., Ojha, M., Singh, K. P. & Singh, K. (2026). *Retrieval-Augmented Generation and Vocabulary-Constrained Filtering for Ontology Learning.* LLMs4OL 2026. https://arxiv.org/abs/2608.27101
- LLMs4OL 2026 challenge. https://sites.google.com/view/llms4ol2026

**Extraction, schema, benchmarks**

- Caufield, J. H., Hegde, H., Emonet, V., Harris, N. L., Joachimiak, M. P., Matentzoglu, N., Kim, H., Moxon, S. A. T., Reese, J. T., Haendel, M. A., Robinson, P. N. & Mungall, C. J. (2024). *Structured prompt interrogation and recursive extraction of semantics (SPIRES): a method for populating knowledge bases using zero-shot learning.* *Bioinformatics* 40(3), btae104. https://doi.org/10.1093/bioinformatics/btae104 · https://github.com/monarch-initiative/ontogpt
- Mihindukulasooriya, N., Tiwari, S., Enguix, C. F. & Lata, K. (2023). *Text2KGBench: A Benchmark for Ontology-Driven Knowledge Graph Generation from Text.* ISWC 2023, Resources Track. https://arxiv.org/abs/2308.02357 · https://github.com/cenguix/Text2KGBench
- Moxon, S. A. T., Solbrig, H., Harris, N. L. et al. (2025). *LinkML: An Open Data Modeling Framework.* *GigaScience*, giaf152. https://doi.org/10.1093/gigascience/giaf152 · https://linkml.io/ · https://github.com/linkml/linkml
- Bian, H. (2026). *LLM-empowered knowledge graph construction: a survey.* https://arxiv.org/abs/2510.20345

**Competency questions**

- Li, J., Wang, Z., Garijo, D. & Poveda-Villalón, M. (2026). *CQ4OE: A benchmark for assessing LLM-assisted ontology generation from competency questions.* https://arxiv.org/abs/2609.26029
- Talukder, A., Mridul, M. A. & Seneviratne, O. (2026). *Towards Automated Ontology Generation from Unstructured Text: A Multi-Agent LLM Approach.* https://arxiv.org/abs/2604.23090
- Grüninger, M. & Fox, M. S. (1995). *Methodology for the Design and Evaluation of Ontologies.* Workshop on Basic Ontological Issues in Knowledge Sharing, IJCAI-95, Montreal. http://www.eil.utoronto.ca/wp-content/uploads/enterprise-modelling/papers/gruninger-ijcai95.pdf

**Vocabularies**

- ZBW Leibniz Information Centre for Economics. *STW Thesaurus for Economics.* https://zbw.eu/stw/ · JEL mapping: https://zbw.eu/stw/version/latest/mapping/jel/about.en.html
- W3C (2014). *The RDF Data Cube Vocabulary.* https://www.w3.org/TR/vocab-data-cube/
- SDMX cross-domain code lists. https://sdmx.org/sdmx_cdcl/
- Hepp, M. *The GoodRelations Ontology for Semantic Web-based E-Commerce.* http://purl.org/goodrelations/v1#

**Operational ontology**

- Palantir Foundry docs: [ontology overview](https://www.palantir.com/docs/foundry/ontology/overview) · [why build one](https://www.palantir.com/docs/foundry/ontology/why-ontology) · [core concepts](https://www.palantir.com/docs/foundry/ontology/core-concepts) · [action types](https://www.palantir.com/docs/foundry/action-types/overview)
- Palantir. *Palantir for Builders* (AIP Developer Tier). https://www.palantir.com/offerings/palantir-for-builders/

**Cause mapping**

- Markóczy, L. & Goldberg, J. (1995). *A method for eliciting and comparing causal maps.* Journal of Management 21(2), 305–333. https://doi.org/10.1177/014920639502100207
- Laukkanen, M. (1994). *Comparative cause mapping of organizational cognitions.* Organization Science 5(3), 322–343. https://doi.org/10.1287/orsc.5.3.322

**Stack**

- Neo4j: [constraints](https://neo4j.com/docs/cypher-manual/current/constraints/managing-constraints/) · [GRAPH TYPE](https://neo4j.com/blog/developer/graph-type-schema-enforcement-made-easy-preview/) · [Aura quotas](https://neo4j.com/docs/aura/quotas-and-limits/)
- Kuzu (archived Oct 2025, MIT). https://github.com/kuzudb/kuzu
- LadybugDB — Kuzu fork, Arun Sharma. https://github.com/LadybugDB/ladybug
- Vela-Engineering/kuzu — Kuzu fork with concurrent writers. https://github.com/Vela-Engineering/kuzu
- TerminusDB (Apache-2.0). https://github.com/terminusdb/terminusdb · https://terminusdb.org/
- W3C (2017). *Shapes Constraint Language (SHACL).* https://www.w3.org/TR/shacl/
- pySHACL (Apache-2.0, RDFLib). https://github.com/RDFLib/pySHACL
- Apache Jena SHACL (Apache-2.0). https://jena.apache.org/documentation/shacl/
- Foundry-alternative projects checked: https://github.com/cloudbadal007/foundry-ontology-open · https://github.com/smilebank7/OpenFoundry · https://github.com/jachenms/OntoForge
- Angles, R., Bonifati, A., Dumbrava, S., Fletcher, G., Green, A., Hidders, J., Libkin, L., Martens, W., Murlak, F., Plantikow, S., Savković, O., Schmidt, M., Sequeda, J., Staworko, S., Tomaszuk, D., Voigt, H., Vrgoč, D., Wu, M. & Živković, D. (2023). *PG-Schema: Schemas for Property Graphs.* https://arxiv.org/abs/2211.10962
- ISO/IEC 39075:2024. *Database languages — GQL.* https://www.iso.org/standard/76120.html
