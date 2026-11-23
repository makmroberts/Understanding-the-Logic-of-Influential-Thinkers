# Meaning check cut-off (0.40)

The meaning check in `src/annotate/evaluate.py` gives each pair of a hand-drawn step and a model
step a score from 0 to 1 for how close they are in meaning. At 0.40 or more, the two count as
saying the same thing (`settings.yaml`, `meaning.threshold`). This folder holds the pairs that
cut-off was chosen on, so anyone can check it or redo it with human labels (issue #9).

| File | What it is |
|---|---|
| `pairs.json` | The 40 labelled pairs, plus two sets that should never count as the same: 212 pairs of different steps from one hand-drawn map, and 7 main claim vs opposing view pairs |
| `ai_labels.csv` | Each pair's label from three AI raters (Claude Opus 5.5, GPT-6.1 Sol, Gemini 4 Argon) and their majority. No person has labelled these yet |
| `hand_labels.csv` | The same 40 pairs with an empty `label` column, for a person to fill in |
| `pick_cutoff.py` | Scores the pairs with the evaluation's own scorer and finds the best cut |

## How the 40 pairs were chosen

They come from the official runs of the 10 hand-mapped articles under ontology version 2
(commit 22304b2), drawn at random with a fixed seed:

- 18 pairs the box matcher joined by a shared paragraph;
- 10 pairs it joined by role alone (the same slot);
- 12 near misses: a hand step the matcher left unpaired, with the model step at another level
  that cites the most of the same paragraphs.

The step IDs on the model side belong to those version 2 runs, not to the current version 3
runs. Every text is copied in full, so nothing else is needed to redo the check.

## Result with the AI labels

Each pair of raters agreed on 34 of the 40 pairs, and all three agreed on 31. The majority
called 20 pairs same, 15 different and 5 unsure. The unsure pairs are left out.

Cuts of 0.40 and 0.41 separate same from different equally well (87%). At 0.40:

- 16 of the 20 same pairs (80%) score 0.40 or more;
- 1 of the 15 different pairs (7%) does;
- 2 of the 212 pairs of different steps from one hand map (1%) do;
- none of the 7 main claim vs opposing view pairs do.

So the check is strict. It misses about 1 real match in 5, and it rarely calls two different
things the same.

## Labelling by hand (issue #9)

1. Open `hand_labels.csv` (Excel is fine). In the `label` column, write one of:
   - `same`: the same point or the same body of evidence. Different wording, or one sentence
     adding a little detail, still counts as same.
   - `different`: two different things, even on the same topic.
   - `unsure`: only partial overlap, or you cannot tell.

   These are the instructions the AI raters had. Do not look at `ai_labels.csv` first. The
   sheet does not say which sentence is hand-drawn and which is the model's, on purpose.
2. Save it as CSV. Then, from `annotation/`:
   `python calibration/meaning_cutoff/pick_cutoff.py hand_labels.csv`
3. If the best cut moves away from 0.40, change `meaning.threshold` in `settings.yaml` and
   re-score every run with `python -m annotate report`.
