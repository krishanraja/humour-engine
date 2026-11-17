# humour-engine

An inspectable humour comprehension machine. Given a line, a passage or a multi-turn exchange, it returns
the literal reading, any supported comic reading, the mechanism that creates it, evidence spans tied to the
original text, the context the reading depends on, credible alternatives and explicit uncertainty. A readable
explanation is rendered from the same validated object.

This is a general-purpose engine. Krish's personal humour preferences stay in `krishanraja/ai-harness`
and are not built in. A taste profile is an optional input that a caller supplies explicitly.

## Status (2026-11-17)

```text
local implementation:           complete (text and conversation; contracts, core, interfaces, controls)
offline contract checks:        pass (101 tests; 15/15 fixture diagnostics)
real inference:                 not_run (no API key in this environment; adapter built and tested offline)
dataset reuse:                  S01, S02, S06 active; S03 dormant (no experiment needs it); S04, S05 reference only
classifier reproduction:        measured as an independent re-implementation, not a reproduction (see evals/reports)
human comprehension evaluation: pending (annotation machinery shipped; no annotations yet)
personalisation:                candidate_only (explicit-feedback profiles; no feedback configured)
multimodal capability:          text and transcript-as-text only; image/audio/video return unsupported
external publication/deploy:    none
```

Because real inference has not run, this release is **a working integration scaffold with unverified
comprehension performance**. Fixture-mode results are hand-authored and labelled as such everywhere.

## Run it

```bash
pip install -e '.[dev]'
```

```bash
humour doctor
```

```bash
humour analyse -t "The bank promised interest. I am still bored." --fixture
```

```bash
humour analyse -t "Excellent timing." -c "We finished moving every box an hour ago." --fixture --format both
```

```bash
humour evaluate diagnostics --fixture
```

```bash
humour serve   # loopback only: POST /v1/analyse, POST /v1/compare, GET /v1/capabilities, GET /v1/taxonomy
```

```bash
humour mcp     # stdio MCP: humour_analyse, humour_compare, humour_profile_assess, humour_capabilities
```

Live inference (needs `ANTHROPIC_API_KEY` in the environment and per-request permission):

```bash
humour analyse -t "Your line here" --live
```

Fixture mode only answers the registered diagnostic inputs in `data/fixtures/diagnostic_cases.yaml`.
Any other text returns `fixture_missing`. It never makes up an answer.

## Modes

| Mode | What runs | Semantic capability |
|---|---|---|
| live | Anthropic Messages API with forced structured output | comprehension, compare, counterfactual, profile fit |
| fixture | hand-authored responses for registered inputs | same contracts, no inference |
| local_model | TF-IDF + logistic regression on MaryKenneth five-class labels | `styles` and `attribution` only |
| heuristic | nothing semantic ran | none |

## Layout

`src/humour_engine/` holds contracts, taxonomy, corpus, analysis, models, attribution, profiles, evaluation,
interfaces and operations. `knowledge/` holds the ontology, pattern cards and crosswalks. `sources/` holds the
registry and source audit. `evals/` holds protocols, the sealed split manifest, rubrics and reports. `docs/`
holds the architecture, data card, model card, evaluation protocol, runbook and limitations.
