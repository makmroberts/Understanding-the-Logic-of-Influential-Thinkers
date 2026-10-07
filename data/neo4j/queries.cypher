// Starter queries for the argument graph.  http://localhost:7474  (neo4j/argumentmaps)
//
//   (:Document)                 20 articles
//   (:Claim:<Type>)             358 nodes, typed by schema slot
//   (:Concept)                  the hand-built cross-document layer
//   (:Claim)-[:IN]->(:Document)
//   (:Claim)-[:SUPPORTS|LICENSES|BOUNDS|MOTIVATES|RECONSTRUCTS]->(:Claim)  forward
//   (:Claim)-[:REVISES|REBUTS|QUALIFIED_BY|UNDERCUT_BY|DEFERS]->(:Claim)   push-back
//   (:Claim)-[:INSTANCE_OF]->(:Concept)
//
// ===========================================================================
// READ THIS FIRST
//
// The corpus is annotated under THREE templates, and they OVERLAP IN TIME -
// so a date cut does not separate them. Group by `family` instead.
//
//   plain   9 docs  2017-12 -> 2020-02   evidence split into 6 nodes (D1..D6)
//                                        no apparatus, almost no hidden slot
//   banner  6 docs  2020-01 -> 2025-05   the 26-slot experiment: T[] banner,
//                                        LEG legend, ghost slots, Level 1b
//   meta    5 docs  2025-07 -> 2026-02   back to a clean map, %% header
//                                        comments, 2 evidence nodes, longest text
//
// `banner` straddles 2020-2025, so setser_may_5_25 is banner while
// setser_feb_26_20 is plain. Note `meta` resembles `plain`, not `banner`:
// the heavy apparatus was a middle-period experiment that got dropped.
//
// Consequence: any query that COUNTS nodes across families measures your
// annotators, not Setser. Evidence node count falls 6.0 -> 2.5 -> 2.0 per
// article, but the content does not follow it: 347 -> 296 -> 510 chars. So
// `plain` and `banner` record a similar volume at very different granularity,
// and `meta` records clearly the most. Section C shows the artifact.
// Run section A first.
// ===========================================================================


// ===========================================================================
// A. VALIDATE - run these before trusting anything else
// ===========================================================================

// A1. The three-template problem, in one table.
// Node counts move a lot; evidence CONTENT barely does. That gap is the artifact.
MATCH (c:Claim)-[:IN]->(d:Document)
WITH d.family AS family, d, c
RETURN family, count(DISTINCT d) AS articles, min(d.date) AS from, max(d.date) AS to,
       toInteger(1.0 * sum(CASE WHEN c:EvidenceData OR c:EvidenceSource
                                THEN 1 ELSE 0 END) / count(DISTINCT d)) AS ev_nodes_per_doc,
       toInteger(1.0 * sum(CASE WHEN c:EvidenceData OR c:EvidenceSource
                                THEN size(c.text) ELSE 0 END) / count(DISTINCT d)) AS ev_chars_per_doc,
       sum(CASE WHEN c:HiddenAssumption THEN 1 ELSE 0 END) AS hidden,
       sum(CASE WHEN c:RevisedPrior THEN 1 ELSE 0 END) AS revised
ORDER BY from;

// A1b. Proof the templates overlap in time - no date cut separates them.
MATCH (d:Document) RETURN d.date AS date, d.family AS family, left(d.title, 46) AS article
ORDER BY date;

// A2. How much of the edge typing was inferred rather than drawn?
// 201 of 340 edges carry no label and defaulted to SUPPORTS.
MATCH ()-[r]->() WHERE r.labelled = false
RETURN type(r) AS rel, count(*) AS assumed_not_stated;

// A3. How were node types resolved? 'level' is the weakest inference.
MATCH (c:Claim) RETURN c.type_source AS resolved_by, count(*) AS n ORDER BY n DESC;

// A4. Structural bugs: forward edges running backwards against the level order.
// Finds three in setser_jun_4_18, where L4 claims feed an L3 mechanism.
MATCH (a:Claim)-[r {polarity: 'forward'}]->(b:Claim)
WHERE a.level STARTS WITH 'L' AND b.level STARTS WITH 'L'
  AND toInteger(substring(a.level, 1, 1)) > toInteger(substring(b.level, 1, 1))
RETURN a.doc AS article, a.nid + ' (' + a.level + ')' AS from,
       type(r) AS rel, b.nid + ' (' + b.level + ')' AS to;

// A5. Template placeholder text left in the maps.
// Catches setser_feb_26_20 P1, never filled in.
// CONTAINS is case-sensitive in Cypher, hence toLower.
WITH ['never stated, but the argument', 'what they openly take as given',
      'how one thing causes another', 'a second causal channel',
      'what the mechanisms add up to'] AS boilerplate
MATCH (c:Claim)
WHERE any(b IN boilerplate WHERE toLower(c.text) CONTAINS b)
RETURN c.doc AS article, c.nid AS node, c.header AS header, c.text AS placeholder;


// ===========================================================================
// B. SAFE TO INTERPRET - robust to how finely a map was annotated
//
// These ask about SHAPE (what connects to what) and about the hand-built
// concept layer, neither of which depends on node granularity.
// ===========================================================================

// B1. Where does evidence actually attach? The signature of an empirical arguer.
// Answer: 71 of 90 forward edges from L2 land on L3 mechanisms, not conclusions.
// Setser almost never lets a number speak for itself - it always routes
// through a stated causal channel first.
MATCH (e:Claim)-[r {polarity: 'forward'}]->(t:Claim) WHERE e.level = 'L2'
RETURN t.level AS evidence_lands_on, count(*) AS n ORDER BY n DESC;

// B2. Same question for priors - do assumptions drive mechanisms or conclusions?
MATCH (p:Claim)-[r {polarity: 'forward'}]->(t:Claim) WHERE p.level = 'L1'
RETURN t.level AS priors_land_on, count(*) AS n ORDER BY n DESC;

// B3. The hidden work: unstated assumptions that license a conclusion.
// These are the Toulmin warrants - the capstone's most interesting object.
MATCH p = (h:HiddenAssumption)-[:LICENSES|SUPPORTS*1..3]->(k:MainClaim)
RETURN h.doc AS article, h.header AS hidden_assumption, length(p) AS hops
ORDER BY article;

// B4. Ideas he returns to across years (the concept layer).
MATCH (c:Claim)-[:INSTANCE_OF]->(k:Concept)
RETURN k.label AS concept, count(DISTINCT c.doc) AS articles,
       min(c.date) AS first_seen, max(c.date) AS last_seen,
       collect(DISTINCT c.doc) AS appears_in
ORDER BY articles DESC;

// B5. A concept as a subgraph - the same idea argued in different articles.
MATCH (k:Concept {id: 'state-can-direct-purchases'})<-[:INSTANCE_OF]-(c:Claim)
OPTIONAL MATCH (c)-[r]->(c2:Claim)
RETURN k, c, r, c2;

// B6. Where he says he was wrong. Three articles carry a revised prior.
MATCH (r:RevisedPrior)-[:IN]->(d:Document)
RETURN d.date AS date, d.title AS article, r.text AS revised_prior ORDER BY date;

// B7. How he handles opposition: named opponent, or self-issued caveat?
MATCH (c:Claim) WHERE c.level = 'L6'
RETURN c.type AS counterpoint_kind, count(*) AS n ORDER BY n DESC;

// B8. One article's whole argument as a picture. Change the id.
MATCH (c:Claim)-[:IN]->(d:Document {id: 'setser_2025-07-07_china-stealth-surplus'})
OPTIONAL MATCH (c)-[r]->(c2:Claim)
RETURN c, r, c2;

// B9. Full chains from evidence to conclusion in one article.
MATCH p = (e:EvidenceData)-[:SUPPORTS*1..4]->(k:MainClaim)
WHERE e.doc = 'setser_2025-11-12_china-surplus-imf'
RETURN p;

// B10. His signature move: mechanisms that are measurement distortions
// rather than economic channels. Only annotated on the 2024+ maps.
MATCH (m:Mechanism) WHERE m.mechanism_kind <> ''
RETURN m.mechanism_kind AS kind, m.doc AS article, left(m.text, 70) AS mechanism
ORDER BY kind, article;


// ===========================================================================
// C. CONTAMINATED - do not read these as findings about Setser
//
// Each one counts nodes across the 2020 schema change. Keep them only to
// demonstrate the artifact, or re-run them restricted to a single era.
// ===========================================================================

// C1. "Evidence per article collapsed after 2019" - no. Put the two columns
// side by side and the node count falls while the content does not.
MATCH (c:Claim)-[:IN]->(d:Document) WHERE c:EvidenceData OR c:EvidenceSource
RETURN d.date AS date, d.family AS family, left(d.title, 38) AS article,
       count(c) AS ev_nodes, sum(size(c.text)) AS ev_chars
ORDER BY date;

// C2. "He started making hidden assumptions in 2020" - no, the slot was added.
// The one plain-family exception is setser_feb_26_20, which is why a date cut
// made this look like a clean switch.
MATCH (h:HiddenAssumption)-[:IN]->(d:Document)
RETURN d.family AS family, d.date AS date, count(h) AS hidden ORDER BY date;

// C3. Push-back ratio by year. A ratio is less exposed than a raw count, but
// L6 was annotated differently too - treat as suggestive, not measured.
// Add `WHERE a.family = 'meta'` to stay inside one template.
MATCH (a:Claim)-[r]->(b:Claim)
WITH left(a.date, 4) AS year,
     sum(CASE WHEN r.polarity = 'pushes_back' THEN 1 ELSE 0 END) AS pushback,
     count(r) AS total
RETURN year, pushback, total, round(100.0 * pushback / total) AS pct ORDER BY year;
