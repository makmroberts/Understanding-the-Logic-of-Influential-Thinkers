# Source extraction

Scripts for turning public source material into annotation-ready Markdown.
Outputs go to `internal/`, which is gitignored — text stays local, only the
scripts are versioned.

## Current scope

`cfr_extract.py` handles CFR "Follow the Money" articles (Brad Setser).
`sources_followthemoney.csv` is the registry of the 20 articles the team is
annotating, with the per-owner year assignment.

```bash
python scripts/cfr_extract.py --owner sicheng      # 2020 + 2024 set
python scripts/cfr_extract.py --year 2020
python scripts/cfr_extract.py --all                # all 20
python scripts/cfr_extract.py --url https://www.cfr.org/articles/<slug>
python scripts/cfr_extract.py --owner sicheng --no-cache   # force refetch
```

Output: one `YYYY-MM-DD_<slug>.md` per article in `internal/extracted/`, plus
`_manifest.csv`. Raw HTML is cached in `internal/.cache_html/` so re-runs do
not re-hit CFR.

## Verified working (2026-09-30)

Ran against all 7 articles in the 2020/2024 set. All 7 succeeded, 951–2007
words each, first and last paragraph checked by hand against the live pages.

| What | How | Notes |
|---|---|---|
| Fetch | `urllib` + browser UA | No 403, no JS rendering needed, no auth. Server-rendered HTML contains the full body. |
| Body | `<p class="rich-text ...">` | The only selector needed. Catches body text and the trailing footnotes; picks up no nav or boilerplate. |
| Metadata | JSON-LD in the `parsely-*` script tag | Gives headline, author, `datePublished`, `dateModified`, `articleSection`. |
| Inline citations | `<a>` inside body paragraphs, kept as Markdown | Essential — Setser argues by hyperlink, so the cited paper is the evidence node. |
| Figures | `<figure><img src>` on `static.cfr.org` | The **filename is usually the chart title**, URL-decoded. No `<figcaption>` exists, so this is the only caption source. |

Dependencies: Python stdlib only. `bs4`, `lxml`, and `trafilatura` are not
installed in this environment, which is why the parser is regex-based.

## Known issues

- **Date in the article list is wrong for one entry.** "Why Didn't Tariffs Push
  Up the U.S. Dollar?" is listed as July 2024 but CFR dates it **2025-05-05**.
  The extractor uses the CFR date, so the file is named `2025-05-05_...`.
  Strictly this belongs to the 2025 bucket — worth raising with the team.
- **External co-authors are partly lost.** JSON-LD does carry CFR-affiliated
  co-authors (Dylan Yalbir on "Slouching Toward Phase One", Michael Weilandt on
  "China's Record Manufacturing Surplus"). It drops non-CFR ones: Volkmar Baur
  of Union Investment is a co-author of the manufacturing-surplus post but
  appears only in the first body paragraph. Check `p1` and add by hand.
- **Figure titles degrade on some posts.** Most filenames are real chart titles
  ("U.S. Non-petrol Goods Trade..."), but the March 2024 post uses placeholders
  ("1", "second", "ToTal Man Exp"). For those, read the chart off the page.
- Regex parsing is brittle by nature. If CFR restyles the site, the
  `rich-text` selector is the first thing to check — the script prints
  `WARNING: no body paragraphs matched` rather than writing an empty file.

## Scaling up later

This is deliberately small and single-source. For the planned
large-scale extraction skill, the pieces that should generalize are:

1. **Registry-driven selection.** A CSV of `slug,url,owner,...` with
   `--owner`/`--year`/`--all` filters. Swap the CSV, keep the interface.
2. **Per-source adapter.** Only `fetch`, `P_RE`, `parse_jsonld`, and
   `figure_title` are CFR-specific. Splitting those into a source adapter
   (one per publisher: CFR, Substack, LinkedIn, Bridgewater) with a shared
   `render()` is the natural refactor.
3. **Fixed output contract.** Stage 1a in frontmatter, Stage 1b as `TODO`
   slots, body with `<!-- pN -->` anchors, then Figures and References. The
   paragraph anchors matter: argument-map nodes should be able to cite `p7`.
4. **Caching and rate limiting.** Already in place (2s delay, 3 retries,
   SHA-keyed HTML cache). Keep both when parallelizing.
5. **Manifest.** `_manifest.csv` with counts and `page_sha256` is what makes
   re-extraction auditable. Keep it.

Annotation reference lives in `internal/`: `reference/pipeline_structure.md`
(the 3-stage pipeline), `maps/` (one argument map per article), and
`maps/architecture/` (the general architecture and the side-by-side demo).

Do not add more output paths to the repo. Extracted text and caches belong in
`internal/`; anything shared with the team gets exported, not committed.
