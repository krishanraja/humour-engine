# Architecture

## Decision record (2026-11-17)

- **Target:** `krishanraja/humour-engine`, an empty repository whose purpose matches the engine. Built on
  branch `claude/hopeful-cannon-cvibw1`.
- **One Python core.** The research classifiers, corpus tooling and attribution are Python. Pydantic for
  contracts, Typer for the CLI, FastAPI for HTTP, the `mcp` 2.x `MCPServer` for MCP. Every adapter calls
  `interfaces/service.py`, which calls `analysis/core.py`. Prompts, validators and defaults exist once.
- **No vector store, queue or database service.** Card retrieval is lexical over a YAML file and can be
  switched off (`retrieval_mode="off"`) as an ablation. SQLite is used only for run checkpoints and batch
  budgets. Infrastructure is added when a measurement earns it.
- **Licence gates removed** (Ruling, Krish, 2026-11-17: he owns all listed machinery and data). The registry
  still controls provenance, activation, removals and evaluation-only assets, because those protect
  experimental integrity rather than rights.
- **Engine, not a personal profile** (Ruling, Krish, 2026-11-17: ai-harness remains his personal humour
  preferences; this engine is a machine). No personal rules are built in. Profiles are explicit, versioned,
  per-scope inputs.

## Request path

```text
AnalysisRequest (strict schema)
  -> select_context: focus never cut; nearest context first; omission reported; abstain if setup may be lost
  -> choose provider: allowlist + allow_external_inference; empty allowlist = no inference
  -> retrieve cards (lexical; excludes the analysed item and any held-out blocklist)
  -> build prompt (one builder; material JSON-encoded inside <material>; system prompt fixed)
  -> BudgetLedger.reserve -> provider call -> settle actual usage
  -> Candidate (strict) -> one repair call only if budget remains
  -> validate_candidate: exact spans, segment ids, ontology labels, modality guard, psychological-claim guard,
     intent provenance, context-claim provenance, reading consistency
  -> optional bounded second assessment (adds counterevidence, never overrules)
  -> styles / attribution / profile_fit / counterfactual tasks
  -> AnalysisResult (completion invariants enforced by the model validator)
  -> render_markdown(result)
```

## Module map

| Module | Responsibility |
|---|---|
| contracts | requests, results, comparison, corpus records, profiles (schema version 1) |
| taxonomy | ontology axes, pattern cards, crosswalks, release validation |
| corpus | registry-gated importers, canonical identity, grouping, sealed split manifests |
| analysis | context selection, prompt, candidate schema, validation, core, compare, render, retrieval |
| models | provider adapters (fixture, Anthropic), style classifiers |
| attribution | LIME-style word-removal attribution over the full style-model path |
| profiles | build candidate from explicit feedback, assess fit, evaluate on withheld feedback, store |
| evaluation | diagnostics, metrics, style experiment, annotation tooling, live-run plan, reports |
| interfaces | service layer, CLI, HTTP, MCP |
| operations | registry, budget ledger, run store, cache |

## Staged research runs

`operations/runs.py` gives each stage an output file, a version and a recorded hash. A stage is complete only
when its output exists and matches. Missing or altered outputs rerun the stage; empty outputs fail. Attempts
persist across restarts. A changed input seal needs a new run id. The style experiment uses stages
`split`, `train_select` and `test_eval`. A test ledger refuses to reuse a sealed test with a different frozen
configuration.
