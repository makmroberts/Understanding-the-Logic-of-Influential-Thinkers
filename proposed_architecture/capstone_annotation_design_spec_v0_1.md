# Capstone: Ontology-Driven Article Annotation Pipeline
**Working technical design — v0.1 (proposed, October 31, 2026)**

## 1. Purpose and status
Develop an automated, inspectable pipeline that converts source articles into structured representations of the author's argument. The annotation JSON is the canonical output. The knowledge graph and Mermaid/Obsidian visualizations are downstream, reproducible derivatives. The design must remain functional when an argument ontology is replaced or updated without rewriting pipeline code, provided it obeys the same configuration interface.

**Status:** This is a draft contract to review with the team. Example annotations adapted from the legacy Mermaid map are illustrations, not newly verified extractions.

## 2. Conceptual separation and ownership
| Component | Defines / owns | Must not define |
|---|---|---|
| `ontology.yaml` | Permitted flat argument roles and relationship IDs, meanings and directed-edge semantics; optional role-family mappings; extract/validation guidance | Specific article nodes; mandatory flowchart levels; economic facet terms |
| `facets.yaml` | Controlled, cross-ontology economic subject terms, geo subject/counterpart, cardinality, inheritance and alignment | Argument role classification or edge meanings |
| `competency_questions.yaml` | Query shapes, retrieval requirements, regression fixtures, and governance of facet vocabulary | Mandatory article flowchart |
| Article JSON | Article identity, source references, run metadata, annotated nodes and directed edges, facet assignments and review state | The definitions of the roles and facet terms it refers to |
| Raw article record | Canonical text, stable paragraph IDs, actual hyperlinks and citation locations | Model interpretation of the argument |
| Knowledge graph export | Selected representation and cross-document joins, without deleting canonical annotations | Authoritative replacement for the article JSON |

Existing `schema_map.yaml` also includes Mermaid header/class/level parsing, arrow default, and layout-operator migration rules. Those are **legacy migration logic**, not rules for direct-from-text LLM annotation. Keep them available to parse old maps, but do not require a new article to contain levels L0–L6 or interpret `~~~` as reasoning.

## 3. File and version contract
Recommended directories (proposed):
- `config/ontology.yaml`
- `config/facets.yaml` (existing content preserved at first)
- `config/competency_questions.yaml` (existing content preserved at first)
- `data/articles/<article_id>.*` — cleaned canonical source and paragraph IDs
- `data/annotations/<article_id>.json` — canonical annotation
- `data/review/` — review queues or decisions
- `outputs/` — generated graphs and visualizations

Each annotation records `schema_version`, the ontology **ID and version**, facet version, pipeline version and actual annotation timestamp. Null timestamps in the example mean not yet run. On re-annotation, preserve an earlier version or revision history in the repository; don't silently reuse IDs if the represented statement changes meaning. Opaque IDs such as `n001` are article-scoped; the global key is `<article_id>#<node_id>` (and an annotation revision identifier should be included in external citations if revisions are tracked). An ID must not encode its role.

## 4. Canonical article JSON: top level
The companion `proposed_article_annotation_example.json` is a syntactically valid, **partial** worked example, not the complete article's 13-node map.

| Key | Type | Required | Rule / population |
|---|---|---|---|
| `schema_version` | string | Yes | Version of JSON data contract, independent of ontology version |
| `article` | object | Yes | Source identity and metadata; deterministic extraction preferred |
| `annotation` | object | Yes | Provenance for the annotation process and model/tool runs |
| `summary` | object | Yes | Optional-field object with central question, thesis, prose synopsis; LLM may populate |
| `nodes` | array of objects | Yes | Zero or more individual argument statements; LLM first pass |
| `edges` | array of objects | Yes | Zero or more meaningful, directed argumentative links; LLM first pass |
| `validation` | object | Yes | Overall status, deterministic checks, human-review queue |
| `extensions` | object | No | Provisional entity/source enrichments; not binding in v1 |

**Not in the v1 contract:** top-level `groups` or machine-readable numerical `facts`, and claim-level `temporal_scope`. Consolidation can later be added as a separately versioned derivative without losing source nodes.

### 4.1 `article`
| Field                         | Type             | Requirement             | Notes                                                                         |
| ----------------------------- | ---------------- | ----------------------- | ----------------------------------------------------------------------------- |
| `id`                          | string           | required                | Stable, source-level article identifier                                       |
| `title`                       | string           | required if recoverable | Preserve exact published title                                                |
| `authors`                     | array of strings | required                |                                                                               |
| `published_date`              | ISO date or null | required key            | `YYYY-MM-DD` when known                                                       |
| `url`                         | URL or null      | required key            | Published page                                                                |
| `publisher`, `series`         | string or null   | optional                | Publication and series                                                        |
| `source_text.path`            | string or null   | required key            | Local canonical extracted article record; not assumed to exist from URL alone |
| `source_text.paragraph_count` | integer or null  | required key            | Count from the canonical extraction                                           |
| `source_text.content_hash`    | string or null   | optional                | Detect source drift; hashing method to be specified                           |
| `references`                  | array            | provisional             | Article-wide hyperlinks / references                                          |
| `metadata_extension`          | object           | optional                | Namespaced additions without changing core arguments; to be defined           |

Canonical source paragraphs should be stored once, outside the annotation JSON; source references within nodes use the stable paragraph IDs (`p1`, `p2`...). If extraction changes paragraph segmentation, update source revision and review dependent references.

### 4.2 `annotation`
Required keys: `annotated_at` (ISO 8601 timestamp or null before execution), `ontology` (`id`, `version`), `facets_version`, `pipeline_version`, `status` (`draft`, `needs_review`, `approved`, `rejected`), and `runs` (array).

Each `runs` entry includes `run_id`, `stage`, `method` (e.g. deterministic / llm / human), `model` (nullable), `parameters` (object), and `timestamp`. Store model provider and exact model revision when available; any API or local-model request identifier can be added. Keep run configuration once and refer to it from nodes/edges. The run record supports reproducibility, not a claim that model decisions are correct.

### 4.3 `summary`
`central_question`, `main_thesis`, and `argument_summary`: each string or null. This section is a navigation summary, **not a substitute** for typed argument nodes. If there are multiple main conclusions, the node collection should preserve all of them rather than forcing a single main claim.

## 5. Canonical node schema
| Field               | Type            | Required | Semantics                                                                                          |
| ------------------- | --------------- | -------- | -------------------------------------------------------------------------------------------------- |
| `id`                | string          | Yes      | Stable opaque article-scoped ID (`n001`); unique among nodes                                       |
| `legacy_id`         | string or null  | Optional | E.g. `P3`, `C1`, `K` only during mapping of older charts                                           |
| `role`              | string          | Yes      | Exact ID present in active ontology `roles`                                                        |
| `content.text`      | nonempty string | Yes      | One meaningfully attributable proposition or argument component; retains qualifiers                |
| `content.label`     | string or null  | Optional | Short UI title, not an additional substantive claim                                                |
| `content.explicit`  | boolean or null | Yes key  | Whether statement is directly expressed; false is not automatically erroneous                      |
| `source.passages`   | array           | Yes      | One or more passage-link objects                                                                   |
| `facets`            | object          | Yes      | Keys and terms validated against `facets.yaml`; empty arrays permitted subject to facet validation |
| `attributes`        | object          | Yes      | Optional role-specific values, only if declared in ontology; empty by default                      |
| `provenance.method` | string          | Yes      | E.g. `llm`, `human`, `legacy_map_adaptation`                                                       |
| `provenance.run_id` | string or null  | Yes key  | Must match annotation run if populated                                                             |
| `review.status`     | enum            | Yes      | `pending`, `approved`, `rejected`, `needs_revision`                                                |
| `review.reasons`    | string array    | Yes      | Controlled issue codes; can be empty                                                               |

Nodes need not carry every role or have a fixed number of incoming/outgoing edges. Prefer independently citable claims or observations in first-pass extraction; don't over-split inseparable propositions merely to increase node count. Never change a node ID solely because the role is corrected.

### 5.1 Node-local passage links
Each entry in `source.passages` has: `paragraph_id` (required), `relation` (`states`, `abstracts`, `presupposes`, `elsewhere`; nullable if not adjudicated), `link_method` (e.g. `llm_proposed`, `deterministic_match`, `human_confirmed`, `legacy_passage_candidate`), `anchor_grade` (`anchored`, `candidate`, `none`, nullable before validation), `review_status` (`pending`, `approved`, `rejected`), and optional `source_excerpt`.

**Important distinctions:**
- `relation` describes what the paragraph *does* for the claim; it is **not** an argument-edge relation.
- `anchor_grade` describes deterministic lexical/literal anchoring, **not truth or model confidence**. A high cosine is not verification. `anchored` doesn't by itself establish that a paraphrase is faithful.
- Human acceptance is captured separately in `review_status`.
- Unstated assumptions may be appropriately `presupposes`, with no direct quotation and a mandatory review flag.
- Store multiple paragraph links for distributed evidence; don't silently keep only the top-scoring one.
- Any corrected attribution needs an auditable review decision (external review log or later revision record), rather than erasing the history of a previous automated suggestion.

### 5.2 Node facets
**Preserve the existing closed vocabulary and its structure**: variable, country, bloc, instrument, data_basis. Country and bloc terms can carry `subject` or `counterpart`, and the `where` group spans both. Proposed JSON representation: each facet key holds an array of assignments, each of which has `term`, `assignment_source` (`hand`, `llm`, `inherited`), optional `run_id`, and `geo_role` for country/bloc only. The first draft explicitly stores assignment-level provenance rather than only a node-level model ID. This is a proposed serialization of existing facet semantics, not a redesign of the term list.

Use `facets.yaml` for assignment cardinality, valid values, geographic subject/counterpart constraints, and inheritance. Flag violations rather than silently making untraceable repairs. Current source rules may deterministically repair certain missing geography assignments, but repaired values must retain `assignment_source: inherited` and be reviewable.

## 6. Canonical edge schema
| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | Yes | Unique opaque article-scoped edge ID |
| `from` | string | Yes | Existing source node ID |
| `to` | string | Yes | Existing target node ID |
| `relation` | string | Yes | Exact ID from ontology `relations` |
| `provenance.method` | string | Yes | E.g. LLM inference, legacy map label, human |
| `provenance.run_id` | string or null | Yes key | Extraction stage reference when applicable |
| `provenance.legacy_label` | string or null | Optional | Preserve former Mermaid text if migrating |
| `review.status` | enum | Yes | `pending`, `approved`, `rejected`, `needs_revision` |
| `review.reasons` | array | Yes | Reason codes; empty if none |

Edges are **argumentative** connections, not automatically economic causal links. Direction is relation-specific and must be defined in ontology descriptions: for `qualified_by`, `from` is the qualified claim and `to` is the caveat; for `undercut_by`, `from` is attacked and `to` is the alternative/undercutting claim. Do not add a link merely because paragraphs are adjacent, facets overlap or Mermaid layout requires it. Signed polarity may be computed from ontology at graph-export time; weights and numerical confidence are out of scope in v1. Cross-article edges are outside the per-article example and need a separate future contract.

## 7. Argument ontology configuration interface (`ontology.yaml`)
The companion `proposed_ontology.yaml` includes the **26 role IDs** enumerated in the uploaded `schema_map.yaml` role-family mapping and **11 relation IDs**, including `frames`. It deliberately omits diagram levels and Mermaid parsing defaults. Its individual role descriptions are **new draft glosses** and require team approval; `schema_map.yaml` provides identifier mappings and families but not complete LLM-ready definitions for every role.

| Section | Purpose |
|---|---|
| `ontology` | ID, version, name, intended use, lineage |
| `roles` | Flat role ID -> description, optional role-specific attribute schema and extraction guidance |
| `relations` | Relation ID -> definition, direction convention, derived argumentative sign |
| `optional_role_families` | Non-binding roll-ups to `oper` and Toulmin families for comparison; no fixed stages |
| `extraction_rules` | General guidelines for missing/unknown roles, unsupported edges and desired proposition granularity |
| `legacy_migration_note` | Clear boundary between new extraction and old Mermaid parsing |

The generic pipeline reads roles/relations dynamically from this file and validates emitted IDs accordingly. New ontologies must satisfy the **same config interface**; changing the ontology's terms or their definitions should not require changing extraction code. A change to the interface itself does require a schema migration. The ontology file is not an article's actual argument and must not enforce a fixed order, number of roles, or complete flowchart.

`competency_questions.yaml` currently governs `facets.yaml`, including retrieval fixtures that reference specific role IDs. Keep this file separate for now. A genuinely new role vocabulary may require adapting the **retrieval fixtures and role filters**, even if extraction and graph export remain generic; complete end-to-end ontology interchangeability is therefore a **design goal**, not yet an established capability.

## 8. Validation and review contract
Run checks in layers:
1. **Parse/schema**: JSON valid, required keys/data types, permitted enumerations.
2. **Referential integrity**: unique IDs; edge endpoints exist; node run IDs exist; article and source-record IDs match.
3. **Ontology**: all roles and relations allowed; optional role-specific attributes valid; no role order/template enforcement.
4. **Facets**: only terms in controlled facets; cardinalities, where-axis, counterpart and inheritance semantics satisfied; preserve assignment provenance.
5. **Source**: every cited paragraph exists in the correct source revision; recorded excerpts match source where applicable; article hyperlinks and citations resolve or are flagged; independent deterministic anchor checks do not disagree silently with model-stated provenance.
6. **Logical/review**: flag hidden assumptions, weak/absent citations, ambiguous roles, questionable edge direction and conflicting evidence; queue for human review. Deterministic checks can test consistency, **not semantic truth**.
7. **Export readiness**: choose a documented policy for pending annotations and reject/flag unreviewed or unverifiable links in trusted graph exports.

Example issue codes: `hidden_assumption`, `unverified_passage`, `missing_passage`, `missing_verified_passage`, `unknown_role`, `unknown_relation`, `invalid_facet`, `unknown_paragraph`, `uncertain_edge_direction`, `unsupported_citation`, `unreviewed_legacy_default`. The review queue can contain the object ID, check ID, reason, status, reviewer and time. Record actual checks once implemented; the example's empty `checks` array does **not** indicate passing validation.

## 9. Proposed deterministic + LLM workflow
| Stage                    | Input -> output                                                                    | Ownership (proposed)                                                    |
| ------------------------ | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1. Ingest                | URL/text -> canonical article, numbered paragraphs, hyperlinks, metadata           | Deterministic parser                                                    |
| 2. Resolve configuration | Config ID/version -> current role+relation vocabulary and independent facets       | Deterministic loader                                                    |
| 3. Extract               | Article + ontology -> fine-grained nodes and meaningful edges                      | LLM, constrained structured output                                      |
| 4. Label facets          | Article + nodes + `facets.yaml` -> facet assignments                               | LLM; deterministic closed-vocabulary validation                         |
| 5. Source linking        | Nodes + canonical article -> paragraph candidates and anchoring                    | LLM proposals plus deterministic checks; preserve all relevant passages |
| 6. Validate              | Article JSON + config + source -> checks / review items                            | Deterministic; human review for ambiguous semantics                     |
| 7. Persist               | Validated annotation + revision record -> canonical JSON                           | Deterministic                                                           |
| 8. Build and export      | Approved or explicitly qualified annotations -> knowledge graph, Mermaid, Obsidian | Deterministic; no loss of canonical source/provenance                   |

Exact sequence of extraction/facet/source-linking calls may change as tool research proceeds; this diagram defines responsibilities, not a mandatory orchestration library. In particular, a structured-output SDK or Pydantic can enforce shape, but cannot independently prove faithfulness of hidden assumptions or edge semantics.

## 10. Worked-example migration and limitations
The included JSON contains three **legacy-map-derived** nodes (`P3`, `C1`, `K`) and two edges, remapped to `n001`, `n002`, `n003`. It illustrates the new shape but does **not** claim that a new LLM inferred them. The working example's `P3` passage was originally `p7` and is suggested for `p26` review, not verified. `C1` has a candidate passage at `p25`. The main claim `K` currently lacks a verified passage match. Legacy unlabelled solid-arrow support was a convention, not a source-asserted fact, and is flagged as such in the example edge.

The legacy current map retains 13 broad claims and 18 links; a fine-grained first-pass output may have a different node count. No node/edge count is mandated by the ontology. Future evaluation should test completeness, relation accuracy, passage attribution and human agreement, not simply graph isomorphism with the legacy hand-drawn chart.

## 11. Deliberately deferred decisions / collaborator review
- **Isaac:** finalized metadata, hyperlink/citation/reference schema; how named organizations/persons are represented; source extraction and versioning.
- **Sicheng:** structured-output interface, model/runtime choices, orchestration approach, run records and errors.
- **Team:** approve or revise new *definitions* in `proposed_ontology.yaml`; settle review thresholds, acceptance policy and gold-standard evaluation set.
- **Later:** group/consolidate annotations without source loss; sparsification policy; role-ontology update workflow and migration; claim-level time horizons; structured numerical fact objects; cross-article concept identity and cross-article edges; ontology-specific competency-question governance.

## 12. Source basis
Prepared from the supplied `schema_map.yaml`, `facets.yaml`, `competency_questions.yaml`, China article Mermaid annotation, `WORKED_EXAMPLE.md`, `PROCESS.md`, October 30 meeting notes, and the design decisions agreed during this conversation. Files differ in revision-era statistics and prose comments; this document uses their **declared vocabularies and contracts** rather than treating all embedded counts as current verified measurements.
