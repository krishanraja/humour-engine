# Source audit (2026-11-17)

All sources are owned by Krish (Ruling, 2026-11-17), so this audit records provenance and use, not rights.
Checkouts were inspected at the commits below. Asset hashes are in `registry.yaml`.

| ID | Source | Commit | What is actually there | Decision |
|---|---|---|---|---|
| S01 | MaryKenneth/XAI_humour_styles | 0eaaef08 | 293 LIME PNGs, 293 per-joke JSON files, `progress.json`, `XAI.xlsx` (293 rows, 1,489 columns, mostly empty), README. No code, no weights, no tests. | **Use as evidence.** Imported as machine predictions, attributions and descriptive measurements, separate from labels. Texts fully overlap S02. |
| S02 | MaryKenneth/Two_Model_Humour_Style | 23a04097 | `Humour_style.xlsx` (1,463 rows, 5 labels), `Humour_style_4classes.xlsx` (same 1,463 texts, 4 labels), `af_ag_train.csv` (448) and `af_ag_test.csv` (120), notebooks, `data_preprocessing.py`. No weights, no inference API. | **Independently implemented method; data active.** Upstream splits ignored. |
| S03 | orionw/rJokesData | d48bedd7 | Gzipped train/dev/test TSV (score, joke), full JSON dump. | **Deferred (dormant).** No current experiment needs popularity scores. Score is a platform engagement signal, never a style or funniness label. |
| S04 | emiljoswin/Deep-Humor... | d76a67f8 | 2020-era notebooks (BERT, GPT-2, CNN/RNN), `joke-no-joke.xlsx`, `news_non_joke.txt`. | **Reference only.** Its joke-vs-news setup motivates the register-confound negative controls in the fixture pack. |
| S05 | vadim0x60/awesome-artificial-humour | 75b73a32 | Bibliography README. | **Reference only.** Discovery index; nothing ingested. |
| S06 | iabufarha/iSarcasmEval | dfc708b5 | English train (3,467 non-empty rows, 867 with an author-written non-sarcastic rephrase) and six ironic-speech categories; task A/B test files. | **Active.** Train file used for contrastive live-run items; test A registered evaluation-only. |
| ENG | engine fixtures and card examples | n/a | Original, author-written, unreviewed. | **Active.** Engineering fixtures, not gold labels. |

## Findings from inspection

- **The MaryKenneth views are one dataset, not four.** 3,787 imported records collapse to **1,463 distinct
  texts**. The four-class, binary and XAI files reuse the five-class texts. Counting them separately would
  inflate sample size and leak across splits. The engine assigns one family-grouped split and derives every
  label view from it.
- **No label conflicts** were found across the views for any shared text.
- **4 near-duplicate pairs** (char TF-IDF cosine ≥ 0.85) are co-located in one partition and listed for human
  review. They are not merged.
- **XAI JSON fields are JSON strings.** Some, such as `primary_emotion: "joy     : 0.992"`, are not JSON. They are
  parsed strictly, never `eval`'d, kept raw with a warning when invalid, and bounded in size.
- **The XAI predictions come from the upstream GTE+XGBoost model.** They are stored as `produced_by: model`
  and never used as labels.
- **Upstream notebook behaviours not reproduced:** the DistilBERT helper's relabelling of low-confidence
  affiliative predictions as aggressive, independent per-view splits, and notebook paths that do not match
  committed files.
- **S01's heuristic counts** (puns, homonyms, "semantic conflicts") are measurements to audit. A homophone
  count of 6 for an ordinary sentence does not establish wordplay.
