# Style classifier experiment: style-mk5-v1

Task: MaryKenneth five-class humour-style labels (self-enhancing, self-deprecating, affiliative, aggressive,
neutral). Source-specific social-function prediction; not a measure of humour comprehension.

## Data
- Records imported: 3787 across the five-class, four-class, binary and XAI views
- Distinct texts after canonical identity: 1463 (label views collapse onto the same texts)
- Split groups (families): 1459; near-duplicate candidates co-located pending review: 4
- Label conflicts across views: 0
- Partition texts: calibration 167, dev 212, test 202, train 882
- Split claim: joke-family disjoint. Not author- or source-disjoint (no such metadata exists).

## Frozen configuration
- Config hash `ab27d55557f338a0`, manifest seal `59068e3445082737`
- single: C=8.0 chosen on dev (dev macro-F1 0.6537), temperature 1.0086
- hierarchical: C=4.0 chosen on dev (dev macro-F1 0.6273), temperature 0.8686

## Sealed test (202 texts, evaluated once)

| System | Macro-F1 | Accuracy | Brier (calibrated) | Brier (raw) | ECE |
|---|---|---|---|---|---|
| Majority baseline | 0.0755 | 0.2327 | 1.5347 | | |
| single | 0.6018 | 0.6238 | 0.4891 | 0.489 | 0.089 |
| hierarchical | 0.6148 | 0.6337 | 0.49 | 0.4952 | 0.0917 |

- Hierarchical minus single, macro-F1: 0.013 (paired bootstrap 95% CI [-0.0149, 0.0433], 202 independent texts).
- Single minus majority baseline: 0.5263 (95% CI [0.4579, 0.5958]).

### Per-class (single)
| Class | P | R | F1 | Support |
|---|---|---|---|---|
| affiliative | 0.4412 | 0.4286 | 0.4348 | 35 |
| aggressive | 0.5806 | 0.766 | 0.6606 | 47 |
| neutral | 0.8667 | 0.7959 | 0.8298 | 49 |
| self-deprecating | 0.5769 | 0.4167 | 0.4839 | 36 |
| self-enhancing | 0.6 | 0.6 | 0.6 | 35 |

### Per-class (hierarchical)
| Class | P | R | F1 | Support |
|---|---|---|---|---|
| affiliative | 0.4688 | 0.4286 | 0.4478 | 35 |
| aggressive | 0.5538 | 0.766 | 0.6429 | 47 |
| neutral | 0.8864 | 0.7959 | 0.8387 | 49 |
| self-deprecating | 0.6154 | 0.4444 | 0.5161 | 36 |
| self-enhancing | 0.6286 | 0.6286 | 0.6286 | 35 |

Denominator: {'abstained': 0, 'answered': 202, 'eligible': 202, 'excluded': 0, 'failed': 0}

## Reading
- Deployed variant (chosen on dev, not test): single
- The hierarchical routing is a hypothesis; this run does not establish an improvement unless its CI excludes zero.
- Not a reproduction of the upstream papers: different features (TF-IDF, not GTE/DistilBERT), and an engine-assigned split.
- Small test set; per-class supports are 35 to 50 texts, so per-class numbers are noisy.
