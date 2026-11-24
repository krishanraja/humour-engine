---
as_of: 2026-11-17
---

# NOW: humour-engine

**What it is.** The fleet's one definition of humour: ontology, pattern cards, prompts and validators, and an engine that reads text or a conversation into readings, mechanisms, evidence, context and uncertainty.

## Where it is right now

<!-- north-star-state {"week_of":"2026-11-23","week_target":null,"current":null,"current_as_of":null,"current_source":"evals/ human evaluation of the bounded live run","urgency":null,"urgency_reason":"not measured yet: the bounded live run and its human evaluation have not run"} --> **North Star number: not measured yet.** Human-judged mechanism accuracy on the sealed set, at least 10 points above the plain-prompt baseline by 22 February 2027 (set by Krish, 2026-11-24).

- Local vertical slice complete: text and conversation analysis with evidence spans, context, uncertainty;
  compare; profile fit; counterfactual on supplied variants; CLI, HTTP (loopback) and MCP.
- Style classifier measured on a sealed family-grouped test (202 texts): macro-F1 0.60 (single), 0.61
  (hierarchical, gain within noise), 0.08 majority baseline.
- Consumer surface: `humour_engine.concept` (CONTRACT_VERSION 1.0) plus `schemas/` for other repositories.
- Real inference: not run. Human evaluation: pending. Personalisation: candidate only.

## What is next and what is waiting on Krish

- Next (2026-11-17): approve the bounded live run (`evals/protocols/live_run_plan.json`) and supply an API key outside the repo.

## What changed recently

- 2026-11-17: [engine vertical slice](docs/history/2026-11-17-engine-vertical-slice.md)
