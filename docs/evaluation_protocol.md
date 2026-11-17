# Evaluation protocol

Claims are reported separately: detection, style classification, comprehension, evidence grounding,
attribution, audience preference and operational reliability. There is no composite "humour score".

## 1. Engineering acceptance (offline, deterministic)

`pytest` covers schema validity, evidence resolution, Unicode offsets, label mappings, registry enforcement,
split integrity, retrieval leakage, injection, isolation, budgets, recovery and interface equivalence.
`humour evaluate diagnostics --fixture` runs the fixture pack. Passing these proves implementation behaviour
only, not comprehension.

## 2. Style classification (measured)

Pre-registered in `evaluation/style_experiment.py`: one sealed split, C chosen on dev, temperature fitted on
calibration, test opened once and logged in a test ledger. Primary metric is macro-F1. Hierarchical versus
single is compared with a paired bootstrap 95% CI over independent texts. Per-class P/R/F1, Brier, ECE and
coverage-error are also reported, with full denominators.

## 3. Comprehension (pending: needs live inference and human judges)

1. **Pilot:** 120 distinct item families with 3 independent annotators each, using
   `evals/protocols/annotation_guide.md` and `humour annotate export` (Label Studio). Essential elements are
   written **before** annotators see any system output. Report Fleiss' kappa and the adjudication rate.
2. **Systems:** `plain`, `ontology` and `engine` on identical inputs and output budgets
   (`humour evaluate plan-live`). An ablation drops retrieval or the second assessment.
3. **Scoring:** essential-element coverage, unsupported-claim rate and contradiction rate, plus blinded
   pairwise judgements (`evaluation/annotation.pairwise_packet`) with randomised A/B order and hidden identity.
   The implementer must not be the sole judge.
4. **Denominators:** for every system, eligible = answered + abstained + unsupported + failed + excluded.
   Timeouts and malformed outputs are never dropped. Quality is compared at matched coverage.
5. **Uncertainty:** computed at item-family level. Annotators and paraphrases of one item are not
   independent samples.
6. **Sealed test:** about 240 independent families, registered after the pilot with thresholds frozen first.

## Proposed targets (to ratify after the pilot; not results)

- Engine beats `plain` on the human comprehension measure, with a paired 95% CI excluding zero.
- At least 60% wins among non-tied pairwise comparisons, reported with ties and missing judgements.
- No rise in unsupported interpretations or neutral false positives at matched coverage.
- If the engine does not beat the simple baseline, keep the simpler route and report that.
