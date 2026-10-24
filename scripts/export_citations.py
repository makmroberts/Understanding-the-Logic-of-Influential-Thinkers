"""The citation layer: what each article cites, and what that connects to what.

Reads   internal/extracted/*.md  (the links the author actually wrote)
        data/nodes.csv, data/node_passages.csv
        scripts/source_urls.yaml, mermaid_code/*.mmd  (`%% url:` wins)
Writes  data/citations.csv        article -> cited source, one row per citation
        data/claim_citations.csv  claim -> cited source, via the passage link
        data/citation_report.md   the measured summary

Why this exists. Until now the only cross-article layer was
`scripts/concepts.yaml`, covering 9 of 359 claims by hand, and no link in the
parsed corpus crosses an article. But the authors have been
drawing cross-article links themselves the whole time, in hyperlinks: 7 of the
citations in the corpus point at another article that is ALSO mapped here. Those
are article-to-article edges with no inference in them at all - the author wrote
the link - so they cost nothing to admit and they are hand-checkable by opening
the page.

Two kinds of edge come out of this, and they are not equally strong:

  article -> source    Direct. The link is in the text. Nothing is inferred.

  claim -> source      Indirect, and it INHERITS THE PASSAGE GRADE. A claim
                       reaches a source only through `node_passages.csv`: claim
                       sits in paragraph p, paragraph p contains link L. If that
                       passage link is `candidate` (semantic overlap only) then
                       the citation is a candidate too and must never be
                       rendered as a source. Grades are never upgraded here.

The second is the one worth having, and it is also the one to be careful with:
it is provenance for free where the passage layer is already `anchored`, and
nothing at all where the passage layer is guessing.

A deliberate non-feature: this does NOT try to identify the author of a cited
source. The host is recorded (`imf.org`, `piie.com`) and that is as far as the
data goes. Mapping a host to an institution to a person is exactly the kind of
inference the project keeps out of code - if the team wants a cited-author axis
it belongs in a hand-maintained overlay next to `source_urls.yaml`, with
`evidence:` on every line.
"""

import argparse
import csv
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTRACTED = ROOT / "internal" / "extracted"
MAPS = ROOT / "mermaid_code"
URL_MAP = Path(__file__).resolve().parent / "source_urls.yaml"

MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")
BARE = re.compile(r'(?<![(\w])(https?://[^\s<>")\]]+)')
PARA = re.compile(r"<!--\s*p(\d+)\s*-->\s*\n(.*?)(?=\n<!--|\n##|\Z)", re.S)

# Hosts that are navigation rather than evidence. Kept deliberately tiny: the
# point of the layer is what the author chose to cite, and pruning it on taste
# would be editing that.
NON_CITATION_HOSTS = {"substack.com", "twitter.com", "x.com"}


def normalize(url: str) -> str:
    """Comparison key for a URL. Query, fragment, trailing slash and the `www.`
    prefix are not part of what was cited."""
    url = url.split("?")[0].split("#")[0].rstrip("/").strip()
    url = re.sub(r"^http://", "https://", url, flags=re.I)
    return re.sub(r"^https://www\.", "https://", url, flags=re.I).lower()


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def doc_urls() -> dict:
    """doc stem -> canonical URL. The map's own `%% url:` beats the overlay -
    the authored artefact outranks anything inferred about it - which
    `link_passages.py` does not currently honour."""
    spec = yaml.safe_load(URL_MAP.read_text(encoding="utf-8")) or {}
    out = {k: v["url"] for k, v in (spec.get("urls") or {}).items()
           if isinstance(v, dict) and v.get("url")}
    for path in sorted(MAPS.glob("*.mmd")):
        m = re.search(r"%%\s*url:\s*(\S+)", path.read_text(encoding="utf-8"))
        if m:
            out[path.stem] = m.group(1).strip()
    return out


def load_extracts() -> dict:
    """normalized url -> {"paras": {n: markdown}, "authors": [...], "file": ...}"""
    out = {}
    for path in sorted(EXTRACTED.glob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^url:\s*(\S+)", raw, re.M)
        if not m:
            continue
        auth = re.search(r"^authors:\s*\[(.*?)\]", raw, re.M)
        out[normalize(m.group(1))] = {
            "paras": {int(p.group(1)): p.group(2) for p in PARA.finditer(raw)},
            "authors": [a.strip().strip('"') for a in (auth.group(1).split(",") if auth else [])],
            "file": path.name,
        }
    return out


def links_in(text: str) -> list:
    """[(label, href)] in order: markdown links first, then naked URLs."""
    out = [(m.group(1), m.group(2)) for m in MD_LINK.finditer(text)]
    for m in BARE.finditer(MD_LINK.sub(" ", text)):
        out.append(("", m.group(1).rstrip(".,;:)")))
    return out


def build(docs, extracts):
    """(citation rows, claim-citation rows). Grades are inherited, never minted."""
    url_to_doc = {normalize(u): d for d, u in docs.items()}

    cites, skipped = [], Counter()
    for doc in sorted(docs):
        ex = extracts.get(normalize(docs[doc]))
        if not ex:
            skipped["no extract"] += 1
            continue
        order = 0
        seen = set()
        for para_n in sorted(ex["paras"]):
            text = ex["paras"][para_n]
            in_footnote = text.lstrip().startswith("[fn")
            for label, href in links_in(text):
                key = normalize(href)
                if host_of(key) in NON_CITATION_HOSTS or key in seen:
                    continue
                seen.add(key)
                order += 1
                cites.append({
                    "doc": doc,
                    "order": order,
                    "para": "p%d" % para_n,
                    "placement": "footnote" if in_footnote else "body",
                    "label": label,
                    "href": href,
                    "host": host_of(key),
                    "source_key": key,
                    # non-empty when the author cited another article in THIS
                    # corpus - a cross-article edge with nothing inferred in it
                    "target_doc": url_to_doc.get(key, ""),
                })

    by_doc_para = defaultdict(list)
    for c in cites:
        by_doc_para[(c["doc"], c["para"])].append(c)

    claim_cites = []
    for row in csv.DictReader((DATA / "node_passages.csv").open(encoding="utf-8")):
        if row["grade"] == "none":
            continue
        for c in by_doc_para.get((row["doc"], row["para"]), []):
            claim_cites.append({
                "doc": row["doc"],
                "node_id": row["node_id"],
                "type": row["type"],
                "para": row["para"],
                # the passage link's grade and relation carry straight through:
                # a candidate passage can only yield a candidate citation
                "grade": row["grade"],
                "relation": row["relation"],
                "href": c["href"],
                "host": c["host"],
                "source_key": c["source_key"],
                "target_doc": c["target_doc"],
            })
    return cites, claim_cites, skipped


def report(cites, claim_cites, docs, extracts, nodes):
    per_doc = Counter(c["doc"] for c in cites)
    hosts = Counter(c["host"] for c in cites)
    distinct = {c["source_key"] for c in cites}
    co = defaultdict(set)
    for c in cites:
        co[c["source_key"]].add(c["doc"])
    shared = {k: v for k, v in co.items() if len(v) > 1}
    xdoc = [c for c in cites if c["target_doc"]]
    cited_as_target = Counter(c["target_doc"] for c in xdoc)

    author_of = {}
    for doc, url in docs.items():
        ex = extracts.get(normalize(url))
        author_of[doc] = (ex["authors"][0] if ex and ex["authors"] else "?")

    anchored = [r for r in claim_cites if r["grade"] == "anchored"]
    claims_any = {(r["doc"], r["node_id"]) for r in claim_cites}
    claims_anch = {(r["doc"], r["node_id"]) for r in anchored}

    L = ["# Citation layer", "",
         "What each article cites, and what that connects to what. Generated by",
         "`scripts/export_citations.py`.", "",
         "An **article -> source** row is direct: the author wrote the link. A",
         "**claim -> source** row is reached through `node_passages.csv` and",
         "**inherits that passage link's grade** - a `candidate` passage yields a",
         "candidate citation, which is a reviewing aid and not a source. Grades are",
         "never upgraded here.", "",
         "## Totals", "",
         f"- {len(cites)} citations over {len(per_doc)} articles, "
         f"{len(distinct)} distinct sources",
         f"- {len(shared)} sources cited by more than one article",
         f"- **{len(xdoc)} citations point at another article in this corpus** - "
         "cross-article edges with nothing inferred in them",
         f"- {len(claims_any)} of {len(nodes)} claims "
         f"({len(claims_any)/max(len(nodes),1):.0%}) reach at least one source; "
         f"{len(claims_anch)} ({len(claims_anch)/max(len(nodes),1):.0%}) do so "
         "through an `anchored` passage",
         ""]

    L += ["## Article to article, inside the corpus", ""]
    if xdoc:
        L.append("| citing article | author | cites | author | placement |")
        L.append("|---|---|---|---|---|")
        for c in sorted(xdoc, key=lambda r: (r["doc"], r["target_doc"])):
            L.append("| `%s` | %s | `%s` | %s | %s |"
                     % (c["doc"], author_of.get(c["doc"], "?"), c["target_doc"],
                        author_of.get(c["target_doc"], "?"), c["placement"]))
        L += ["", "Most cited inside the corpus:", ""]
        for d, n in cited_as_target.most_common():
            L.append("- `%s` - cited by %d" % (d, n))
    else:
        L.append("_None._")

    L += ["", "## Most cited hosts", ""]
    for h, n in hosts.most_common(15):
        L.append("- %3d  %s" % (n, h))

    L += ["", "## Sources cited by more than one article", ""]
    for k, v in sorted(shared.items(), key=lambda kv: -len(kv[1])):
        L.append("- %dx  %s" % (len(v), k))
        L.append("  - " + ", ".join("`%s`" % d for d in sorted(v)))

    L += ["", "## Where each author puts citations", "",
          "Not decoration: it decides whether the passage layer can reach a",
          "citation at all, because a footnote is a different paragraph from the",
          "claim it supports.", "",
          "| author | citations | in body | in footnotes |", "|---|---|---|---|"]
    by_author = defaultdict(Counter)
    for c in cites:
        by_author[author_of.get(c["doc"], "?")][c["placement"]] += 1
    for a, pl in sorted(by_author.items()):
        tot = sum(pl.values())
        L.append("| %s | %d | %d (%.0f%%) | %d (%.0f%%) |"
                 % (a, tot, pl["body"], 100 * pl["body"] / tot,
                    pl["footnote"], 100 * pl["footnote"] / tot))

    L += ["", "## Claim to source, by role type", "",
          "| role | claims reaching a source | of which `anchored` |", "|---|---|---|"]
    tb = Counter(n["type"] for n in nodes)
    ca = Counter(); cn = Counter()
    for r in claim_cites:
        cn[r["type"]] += 1
    for t, total in tb.most_common():
        hit = len({(r["doc"], r["node_id"]) for r in claim_cites if r["type"] == t})
        anch = len({(r["doc"], r["node_id"]) for r in anchored if r["type"] == t})
        if hit:
            L.append("| %s | %d/%d (%.0f%%) | %d |" % (t, hit, total, 100 * hit / total, anch))

    L += ["", "## What this refuses to do", "",
          "- No cited-source AUTHOR is inferred. The host is recorded and stops",
          "  there; host -> institution -> person belongs in a hand overlay with",
          "  `evidence:` on every line, not in this script.",
          "- No claim -> source link is promoted above its passage grade.",
          "- Hosts treated as navigation rather than evidence: %s."
          % ", ".join(sorted(NON_CITATION_HOSTS)),
          ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", action="store_true", help="echo the report")
    args = ap.parse_args()

    if not (DATA / "node_passages.csv").exists():
        sys.exit("data/node_passages.csv missing - run scripts/link_passages.py first")

    docs = doc_urls()
    extracts = load_extracts()
    nodes = list(csv.DictReader((DATA / "nodes.csv").open(encoding="utf-8")))
    cites, claim_cites, skipped = build(docs, extracts)

    DATA.mkdir(exist_ok=True)
    for name, rows in (("citations.csv", cites), ("claim_citations.csv", claim_cites)):
        with (DATA / name).open("w", newline="", encoding="utf-8") as fh:
            if rows:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    md = report(cites, claim_cites, docs, extracts, nodes)
    (DATA / "citation_report.md").write_text(md, encoding="utf-8")

    xdoc = sum(1 for c in cites if c["target_doc"])
    claims = len({(r["doc"], r["node_id"]) for r in claim_cites})
    print("%d citations over %d articles -> data/citations.csv" % (cites and len(cites) or 0,
          len({c["doc"] for c in cites})))
    print("  %d point at another article in this corpus" % xdoc)
    print("  %d claim-source links over %d claims -> data/claim_citations.csv"
          % (len(claim_cites), claims))
    print("  data/citation_report.md")
    for reason, n in skipped.items():
        print("  skipped %d documents: %s" % (n, reason))
    if args.print:
        print()
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
