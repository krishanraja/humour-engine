# Data card

| Dataset | Role | Size used | Labels | Producer |
|---|---|---|---|---|
| S02 MaryKenneth five-class | style classifier train/dev/calibration/test | 1,463 texts | self-enhancing, self-deprecating, affiliative, aggressive, neutral | `imported_unknown` (upstream annotation process not documented in the repo) |
| S02 four-class and binary views | same texts, other label views | folded by canonical id | gate and specialist views | `imported_unknown` |
| S01 XAI analyses | error analysis | 293 texts (all inside S02) | five-class label plus upstream model predictions | labels `imported_unknown`; predictions `model` |
| S06 iSarcasmEval train (En) | contrastive live-run items | 3,467 tweets, 867 rephrases | intended sarcasm and 6 categories | `original_author` (sarcastic flag, rephrase), `human_annotator` (categories) |
| ENG fixture pack | engineering diagnostics | 15 cases, 11 families | expectations only | author-written, unreviewed |

## Split

`evals/split_manifests/mk5-family-split.json`, seal `59068e34...`: train 882, dev 212, calibration 167,
test 202 texts. Grouping uses exact and normalised text identity, parent/derivative links and near-duplicate
candidates. It is **joke-family disjoint only**. No author, source or show metadata exists, so the split makes
no such claims. Overlap checks show 0 texts and 0 families crossing partitions.

## Known confounds

- `neutral` in S02 is a non-humorous control set whose register differs from the jokes. The high neutral
  F1 (0.83) may partly reflect register rather than humour.
- Several S02 texts keep stray typographic quotes. Identity normalisation handles this for deduplication
  only; analysis always sees the raw text.
- iSarcasm rephrases are author-written. They are not guaranteed to be humour-free, so each needs human
  review before it counts as ground truth for a mechanism change.

## Retention

Raw corpora are not committed. Loaders read pinned checkouts verified by sha256. Removals go in
`registry.yaml` under `excluded_records` and are filtered by every importer, so a removed item cannot return
through a rebuilt split, retrieval set or export. Removal mechanics are tested on synthetic fixtures only.
