# Adding a new source

Extraction is source-dependent, so each source gets its own parser. What is shared
is the text format every parser writes. `extractors/metadata.py` reads only that
format, so **a new source should not need any change outside `scripts/parsers/`**.
If it seems to, fix the parser first. A change to the format is a team decision.

## What a parser must produce

Return the doc dict documented at the top of `common.py`, and write it with
`common.render`. That gives the format downstream code relies on:

- a `key: value` metadata block at the top
- numbered paragraphs under `<!-- pN -->` markers, in reading order
- links as `[label](url)`; bare URLs left as written
- footnotes as numbered paragraphs starting `[fnN]` or `*`
- a Figures section with each figure's title, source and `after_paragraph`
- a References section listing each distinct URL once

Parsers that do not go through `common.process` must set `page_sha256` and
`retrieved_at` themselves. Refuse to write an empty document: call `warn_empty`.

## How to build one

1. **Inspect before writing code.** Look at what the source really offers: structured
   metadata, body containers, footers, figures, footnotes, paywalls, and how links and
   quotations appear. Read several documents from different years, since layouts change.
2. **Hold a few documents back.** Build on the rest, then test on those. Results on
   documents you tuned against say little about the next one.
3. **Keep source knowledge in the parser**, as named constants at the top of the file.
4. **Send output to a scratch directory** with `--out` until it passes the checks, and
   do not overwrite the cache of pages already fetched.

## Rules

- **Metadata is deterministic.** No model anywhere in this path, not even as a fallback.
- **Never guess.** If a field cannot be read from the source, leave it empty so the
  extractor flags it. Do not hardcode an author or series that the document does not state.
- **Keep every paragraph the author wrote, and nothing else.** Check the gaps between
  kept blocks for lists and subheads a selector missed, and filter navigation,
  disclaimers and chart labels.
- **Keep every citation**, including bare URLs and links with no visible text. Whitespace
  at a link's edge belongs to the sentence.
- **Do not repair the text.** Leave broken words as extracted and record the problem.
- **Paragraph numbers are citation handles.** Once anything cites a source, changing
  its segmentation means remapping those citations first.
- **Article text stays in `internal/`.** Check the source's license before anything
  derived from it is added to `data/articles/`, and ask first.
- **Nothing new may depend on `mermaid_code/`.**

## Traps already found

| Looks reliable | Why it is not |
|---|---|
| `dateModified` | Stayed at the publication date on a post that had been edited |
| A hash of the whole page | Changes when only the page furniture changes; use `content_hash` |
| `<blockquote>` | Marked the author's own argument as often as real quotation |
| A PDF's `/Author` field | Names whoever typed the file |
| An author's title on the page | Shows the current title, which is wrong on old articles |
| A hardcoded series name | One article was not in the series every other article shared |
| Superscripts, sidebars and chart labels in PDFs | Split lines or get read as body text |

## Before calling it done

- [ ] Compare the output with the raw source by a route that does not reuse the parser:
      paragraph count, and every link by paragraph.
- [ ] Read the first, last and a few middle paragraphs against the original by hand.
- [ ] Run `python scripts/extractors/metadata.py --input <scratch> --out <scratch2>`,
      and explain every flag.
- [ ] Run it again and confirm nothing changes.
- [ ] Test the held-back documents, and report those results separately.
- [ ] Record what worked, what failed and the known limits in `scripts/README.md`.
- [ ] Commit only when explicitly asked.
