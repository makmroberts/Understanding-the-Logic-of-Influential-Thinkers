// Empty lists are not stored, so a citation without a span has no `span_starts`:
// test it with IS NULL, never size(...) = 0, which is null and silently filters out.

// 1. Coverage: claims and argument links per annotated article
MATCH (a:Article)-[:HAS_CLAIM]->(c:Claim)
OPTIONAL MATCH (c)-[r]->(:Claim)
RETURN a.published_date AS date, a.title AS article, count(DISTINCT c) AS claims, count(r) AS links
ORDER BY date;

// 2. The thesis of each article, with what it was asked to answer
MATCH (a:Article)-[:HAS_CLAIM]->(k:MainClaim)
OPTIONAL MATCH (a)-[:HAS_CLAIM]->(q:Question)
RETURN a.published_date AS date, q.text AS question, k.text AS thesis
ORDER BY date LIMIT 5;

// 3. Everything a main claim rests on, any depth, by Toulmin element
MATCH p = (x:Claim)-[*1..6]->(k:MainClaim {kb_doc: 'setser_aug_14_24'})
WITH DISTINCT x, min(length(p)) AS depth
RETURN x.toulmin AS element, depth, x.legacy_id AS id, x.text AS claim
ORDER BY depth, element;

// 4. Exact quotes behind one article's evidence, as citations
MATCH (c:EvidenceData|EvidenceSource|EvidenceDiscrepancy|EvidenceRival {kb_doc: 'setser_aug_14_24'})-[e:CITES]->(p:Paragraph)
WHERE size(e.span_starts) > 0
RETURN c.legacy_id AS id, e.citation AS citation,
       substring(p.text, e.span_starts[0], e.span_ends[0] - e.span_starts[0]) AS setser_wrote
ORDER BY id;

// 5. Keyword search, then follow each hit to the claim it supports
CALL db.index.fulltext.queryNodes('claim_text', 'currency depreciation exports') YIELD node, score
WITH node, score ORDER BY score DESC LIMIT 5
OPTIONAL MATCH (node)-[r]->(target:Claim)
RETURN node.kb_doc AS article, node.role AS role, node.text AS hit, type(r) AS rel, target.text AS bears_on;

// 6. Hidden assumptions: the unstated premises, and what depends on them
MATCH (h:HiddenAssumption)-[r]->(c:Claim)
RETURN h.kb_doc AS article, h.text AS assumption, type(r) AS rel, c.role AS supports_role
ORDER BY article LIMIT 10;

// 7. Where he argues against something: rebuttals and what they target
MATCH (x:Claim)-[r:REBUTS|UNDERCUT_BY|QUALIFIED_BY]->(y:Claim)
RETURN type(r) AS rel, count(*) AS n, collect(DISTINCT x.role)[..4] AS from_roles
ORDER BY n DESC;

// 8. Subject axis: claims about China AND the exchange rate, across articles
MATCH (c:Claim)-[:TAGGED]->(:Term {key: 'country/china'})
MATCH (c)-[:TAGGED]->(t:Term {facet: 'variable'})
WHERE t.term CONTAINS 'exchange-rate'
RETURN c.kb_doc AS article, t.term AS variable, c.role AS role, c.text AS claim
ORDER BY article LIMIT 10;

// 9. What he links to: most-cited outside sources
MATCH (:Paragraph)-[l:LINKS_TO]->(s:Source)
RETURN s.host AS host, count(l) AS links, count(DISTINCT s) AS distinct_urls
ORDER BY links DESC LIMIT 10;

// 10. He cites himself: links from one article in the set to another
MATCH (a:Article)-[:HAS_PARAGRAPH]->(:Paragraph)-[:LINKS_TO]->(:Source)-[:IS_ARTICLE]->(b:Article)
RETURN a.published_date AS from_date, a.title AS from_article, b.published_date AS to_date, b.title AS to_article;

// 11. Integrity: stale citations, uncited claims, excerpts without a span (all should be 0)
OPTIONAL MATCH ()-[e:CITES {source_changed: true}]->() WITH count(e) AS stale
OPTIONAL MATCH (c:Claim) WHERE NOT (c)-[:CITES]->() WITH stale, count(c) AS uncited
OPTIONAL MATCH ()-[x:CITES]->() WHERE x.source_excerpt IS NOT NULL AND x.span_starts IS NULL
RETURN stale AS stale_citations, uncited AS uncited_claims, count(x) AS excerpts_without_span;

// ---------------------------------------------------------------------------------------
// Queries 12 to 15 are about one article: change the name on their first line.
// The article names are the `kb_doc` values, e.g. 'setser_jan_31_20' (query 1 lists titles).
// ---------------------------------------------------------------------------------------

// 12. Sources: every link in one article, in reading order, with where it sits
WITH 'setser_aug_14_24' AS doc
MATCH (a:Article {kb_doc: doc})-[:HAS_PARAGRAPH]->(p:Paragraph)-[l:LINKS_TO]->(s:Source)
OPTIONAL MATCH (s)-[:IS_ARTICLE]->(own:Article)
RETURN p.paragraph_id AS para, l.ref_id AS ref, l.label AS link_text, l.href AS url,
       s.host AS host, l.placement AS placement, own.title AS also_in_this_set
ORDER BY p.position, l.char_start;

// 13. Sources behind claims: which URLs sit in the paragraphs a claim cites
WITH 'setser_aug_14_24' AS doc
MATCH (c:Claim {kb_doc: doc})-[e:CITES]->(p:Paragraph)-[l:LINKS_TO]->(s:Source)
RETURN c.legacy_id AS id, c.role AS role, e.relation AS relation, p.paragraph_id AS para,
       l.label AS link_text, l.href AS url
ORDER BY c.node_id, p.position, l.char_start;

// 14. Review sheet: each claim with its quote, the model's reason, and any flags
WITH 'setser_aug_14_24' AS doc
MATCH (c:Claim {kb_doc: doc})
OPTIONAL MATCH (c)-[q:CITES]->(qp:Paragraph) WHERE size(q.span_starts) > 0
OPTIONAL MATCH (c)-[o:CITES]->(op:Paragraph) WHERE o.span_starts IS NULL       // no span: a context paragraph
WITH c, q, qp, collect(op.paragraph_id) AS context_paras
RETURN c.legacy_id AS id, c.role AS role, c.explicit AS explicit, c.text AS claim,
       q.citation AS citation,
       substring(qp.text, q.span_starts[0], q.span_ends[0] - q.span_starts[0]) AS setser_wrote,
       context_paras, c.reason AS model_reason,
       c.review_status AS status, c.review_reasons AS flags
ORDER BY c.node_id;

// 15. Review sheet for links: each argument step, both ends in full
WITH 'setser_aug_14_24' AS doc
MATCH (a:Claim {kb_doc: doc})-[r]->(b:Claim)
RETURN r.edge_id AS edge, a.legacy_id AS from_id, a.text AS from_claim, type(r) AS relation,
       r.sign AS sign, b.legacy_id AS to_id, b.text AS to_claim,
       r.review_status AS status, r.review_reasons AS flags
ORDER BY r.edge_id;

// 16. The map: one article's claims and argument links, for the Graph view.
//     Click a claim to see its text, reason and review status in the side panel.
WITH 'setser_aug_14_24' AS doc
MATCH (c:Claim {kb_doc: doc})
OPTIONAL MATCH link = (c)-[r]->(:Claim)
RETURN c, link;

// 17. The map with its evidence: the same, plus the paragraphs each claim quotes.
//     Click a CITES arrow to see the citation and the exact words.
WITH 'setser_aug_14_24' AS doc
MATCH (c:Claim {kb_doc: doc})
OPTIONAL MATCH link = (c)-[:SUPPORTS|LICENSES|FRAMES|QUALIFIED_BY|REBUTS|UNDERCUT_BY|MOTIVATES|DEFERS|BOUNDS|RECONSTRUCTS|REVISES]->(:Claim)
OPTIONAL MATCH quote = (c)-[e:CITES]->(:Paragraph) WHERE e.span_starts IS NOT NULL
RETURN c, link, quote;
