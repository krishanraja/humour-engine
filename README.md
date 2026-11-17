# humour-engine

**The shared definition of humour for every repository in the fleet.**

This repository answers one question for any product that has to deal with jokes: *what is actually going on
in this text?* It reports the literal reading, any comic reading the evidence supports, the mechanism that
creates it, the exact words that carry it, the context it depends on, the credible alternatives and how sure
anyone can be. It does not decide what is funny for a brand, a person or an audience. Each consuming engine
keeps its own taste.

```text
              humour-engine (this repo)                        your engine (e.g. growth-heartside)
  ┌───────────────────────────────────────────────┐        ┌──────────────────────────────────────┐
  │ DEFINES   ontology: readings, mechanisms,     │        │ OWNS     voice, style, audience,     │
  │           modes, functions, register, context │  ───▶  │          what to publish, what to cut│
  │ UNDERSTANDS  text → grounded analysis         │        │ USES     labels, evidence, context   │
  │ MEASURES  baselines, splits, human protocol   │  ◀───  │ SUPPLIES optional TasteProfile and   │
  │ NEVER     picks a house style or writes jokes │        │          explicit feedback           │
  └───────────────────────────────────────────────┘        └──────────────────────────────────────┘
```

Krish's personal humour preferences stay in `krishanraja/ai-harness`. They are not built in here.

---

## Contents

1. [Why a shared definition](#1-why-a-shared-definition)
2. [The concept: how this repo defines humour](#2-the-concept-how-this-repo-defines-humour)
3. [What a result looks like](#3-what-a-result-looks-like)
4. [Integrating from another repository](#4-integrating-from-another-repository)
5. [Where your style engine plugs in](#5-where-your-style-engine-plugs-in)
6. [Guarantees you can build on](#6-guarantees-you-can-build-on)
7. [Current status, measured and unmeasured](#7-current-status-measured-and-unmeasured)
8. [Running it](#8-running-it)
9. [Repository map](#9-repository-map)
10. [Changing the definition](#10-changing-the-definition)

---

## 1. Why a shared definition

Every product that writes or screens humorous copy ends up building a half-answer to the same questions.
Is this a joke? Why does it work? Is it sarcastic or sincere? Does it need context the reader will not have?
When each repository answers these differently, its labels cannot be compared, its feedback cannot be pooled,
and its mistakes repeat.

humour-engine makes these answers a shared, versioned dependency:

- **One vocabulary.** "callback", "understatement" and "self_directed" mean the same thing in every
  repository, with written definitions, sincere lookalikes and evidence requirements.
- **One evidence standard.** Every claim points at exact characters in the input. An explanation that cannot
  point at its evidence is rejected, not softened.
- **One honesty standard.** Every result says how it was produced (`live`, `fixture`, `local_model`) and what
  it could not establish. "Not a joke", "ambiguous" and "needs context" are normal answers.

## 2. The concept: how this repo defines humour

Humour here is **a relationship in the material, supported by evidence**, not a property of a topic, a
register or a sentiment. A line is analysed on independent axes, so one line can carry several labels:

| Axis | Question it answers | Values (abridged; full list in `src/humour_engine/knowledge/taxonomy/axes.yaml`) |
|---|---|---|
| `comic_reading` | Does the evidence support a humorous reading? | `supported`, `not_supported`, `ambiguous`, `insufficient_context` |
| `mechanism` | What relationship creates the effect? | ambiguity, incongruity, misdirection, reversal, literalisation, exaggeration, understatement, callback, self_defeating_logic, personification, irony, sarcasm, absurd_reasoning |
| `rhetorical_mode` | What larger approach is in play? | satire, parody, observational, roast, absurdism, meta_humour, wordplay |
| `social_function` | What does it do in this exchange? | affiliative, self_enhancing, self_directed, aggressive, unclear |
| `register` | How is it presented? | mock_formal, bureaucratic, conversational, compressed, textually_understated, acoustically_deadpan (needs audio) |
| `structure` | How is it organised? | one_liner, question_answer, anecdote, dialogue, headline, notice, distributed_sequence, meme_caption |
| `target` | What is mocked or reframed? | self, other_person, behaviour, situation, institution, convention, fictional_person, none, unknown |
| `context_dependency` | What must the reader know? | linguistic, topical, cultural, interpersonal, earlier_turn, visual, acoustic, provided_fact |

Every explanation is built from the same parts: the **literal reading**, the **expectation** the setup creates,
the **trigger** that changes it, the **connecting logic** that makes the second reading coherent, the
**target and perspective**, the **context** relied on, and the **alternatives** still credible.

Principles that keep the definition sharp:

- **A mechanism is not a verdict on quality.** Text can use misdirection and still not be enjoyable.
- **A dark subject is not aggression**, and formal wording is not satire. Surface features are never enough.
- **A word with two dictionary senses is not a pun** unless the text activates both.
- **A callback needs its antecedent.** Without the earlier turn, the answer is `insufficient_context`.
- **Quoted humour belongs to the quoted voice**, not the narrator.
- **No claims about people.** Social function describes the exchange, never a speaker's personality or
  mental state. Text-only input never yields claims about tone of voice, pauses or laughter.

Pattern cards in `src/humour_engine/knowledge/patterns/cards.yaml` make each definition concrete. Each card lists required
evidence, explicitly insufficient evidence, and positive, negative and borderline examples. Crosswalks in
`src/humour_engine/knowledge/crosswalks/` map outside label sets (the MaryKenneth humour styles, iSarcasmEval) onto this
ontology with stated relations: equivalent, broader, narrower, overlapping or unmapped.

## 3. What a result looks like

Input: `"The bank promised interest. I am still bored."` This output was produced with the labelled fixture
provider, and it says so in the result:

```json
{
  "analysis_mode": "fixture",
  "status": "complete",
  "comic_reading": "supported",
  "interpretations": [{
    "id": "i1",
    "is_main": true,
    "literal_reading": "The bank offered interest on savings; the speaker remains bored.",
    "supported_reading": "The speaker pretends 'interest' meant being made interested, and complains the bank failed.",
    "connecting_logic": "One word, two senses. 'Bored' is the opposite of the attention sense, so the second sentence retroactively reinterprets the first.",
    "labels_by_axis": {"mechanism": ["ambiguity", "misdirection"], "rhetorical_mode": ["wordplay"], "structure": ["one_liner"]},
    "evidence_refs": ["ev1", "ev2"],
    "uncertainty": {"score": null, "score_kind": "unknown"}
  }],
  "evidence": [
    {"evidence_id": "ev1", "segment_id": "t1", "start": 18, "end": 26, "exact_text": "interest"},
    {"evidence_id": "ev2", "segment_id": "t1", "start": 33, "end": 44, "exact_text": "still bored"}
  ],
  "limitations": ["FIXTURE MODE: hand-authored, unreviewed response for a registered diagnostic input. Not model inference."]
}
```

Offsets are half-open Unicode code points into the original text, and `exact_text` is always cut from that
text. Confidence is `null` when unknown, never `0`. The same object renders to Markdown with
`render_markdown`, which adds nothing the object does not contain.

## 4. Integrating from another repository

Pick the surface that fits your stack. All four share one core, one prompt and one set of validators, and
return the same result for the same request (tested).

**Python (preferred for Python services).** Import only from `humour_engine.concept`, the stable surface:

```python
from humour_engine.concept import AnalysisRequest, EngineDeps, analyse, define, ontology

req = AnalysisRequest.model_validate({
    "request_id": "post-123",
    "focus_segment_ids": ["t1"],
    "segments": [{"segment_id": "t1", "text": "Excellent timing.", "sequence": 1}],
    "context": {"prior_segments": [{"segment_id": "t0", "text": "We finished an hour ago.", "sequence": 0}]},
    "provider_policy": {"allowed_provider_ids": ["anthropic"], "allow_external_inference": True},
})
result = analyse(req, EngineDeps.default())
if result.comic_reading and result.comic_reading.value == "supported":
    mechanisms = {m for i in result.interpretations for m in i.labels_by_axis.get("mechanism", [])}

define("mechanism", "callback")   # -> "A later turn reapplies an element established earlier."
```

Install it as a dependency pinned to a commit:

```bash
pip install "humour-engine @ git+https://github.com/krishanraja/humour-profile@<commit>"
```

**HTTP (any language).** `humour serve` binds to loopback only, because it has no authentication.

| Route | Purpose |
|---|---|
| `POST /v1/analyse?format=json\|markdown\|both` | analyse an `AnalysisRequest` |
| `POST /v1/compare` | compare two variants or two contexts under one shared budget |
| `GET /v1/capabilities` | configured modes, providers and supported tasks |
| `GET /v1/taxonomy` | the ontology and card index |

**MCP (agents).** `humour mcp` exposes `humour_analyse`, `humour_compare`, `humour_profile_assess` and
`humour_capabilities` over stdio.

**JSON Schema (TypeScript, edge functions, databases).** `schemas/` holds generated schemas for every public
contract plus `ontology.json`. A test fails if they drift from the code. Generate types from them, or
validate stored analyses against them.

## 5. Where your style engine plugs in

This repository stops at understanding. Your engine owns everything about taste. There are three supported
patterns, from loosest to tightest coupling:

1. **Consume labels, keep rules at home.** Call `analyse`, read `comic_reading`, mechanisms, modes, target
   and context dependencies, then apply your own rules (for example "our brand avoids `aggressive`" or
   "never ship a `callback` in a cold email"). Nothing about your preferences enters this repo.
2. **Pass an explicit TasteProfile.** Build a candidate profile from your own approved, rejected and
   pairwise feedback (`profiles/build.py`, `humour profile build`), then request
   `tasks: ["comprehension", "profile_fit"]`. The fit (`match`, `mismatch`, `mixed`, `unknown`) comes back in
   `audience_assessment`, separate from the reading. It never changes whether a reading is supported.
3. **Screen before you publish.** Use `compare` to check a draft against an edited version, or the same line
   under two contexts. Use `missing_context` to catch jokes that only work for people who were there.

Rules for consumers:

- Treat `audience_assessment` as descriptive fit against your own feedback, not a prediction of
  performance, unless you have run the holdout in `profiles/evaluate.py`.
- Never write your preferences into `src/humour_engine/knowledge/`. The ontology defines concepts; taste lives with you.
- Profiles are versioned per owner scope. A server only serves profiles for the scope in
  `HUMOUR_ENGINE_OWNER_SCOPE`, and one scope cannot read or overwrite another's.

## 6. Guarantees you can build on

| Guarantee | Enforced by |
|---|---|
| Requests and results are strict, versioned schemas; unknown fields are errors | `contracts/`, `schemas/` |
| No semantic verdict unless comprehension actually completed | result validator |
| `complete` means every requested task completed; otherwise `partial`, `abstained`, `unsupported` or `failed`, with typed errors | result validator |
| Every evidence span resolves exactly to the original text | `analysis/validate.py` |
| Interpretations citing missing evidence, off-ontology labels, unobserved audio or video, invented intent or personality claims are rejected visibly, and nothing from them leaks into the result | `analysis/validate.py` |
| Fixture output is always labelled and only answers its registered inputs | `models/providers.py` |
| External inference runs only when the request allowlists a provider and sets `allow_external_inference` | `analysis/core.py` |
| Every model call (initial, repair, critic, counterfactual, compare branches) reserves budget first; one shared ledger per comparison; server-side call clamp | `operations/budget.py` |
| Analysed text cannot escape its data block or reach the system prompt | `analysis/prompt.py` |
| Input is ephemeral by default; caching only under explicit retention, scoped per user and keyed on every version | `operations/cache.py` |
| Truncation never silently drops a setup: the engine abstains instead | `analysis/context.py` |

The public surface is `humour_engine.concept` with `CONTRACT_VERSION = "1.0"`. Additive changes bump the
minor version and breaking changes bump the major version.

## 7. Current status, measured and unmeasured

```text
local implementation:           complete (text and conversation)
offline contract checks:        pass (117 tests; 15/15 fixture diagnostics)
real inference:                 not_run (adapter built and tested offline; no API key in the build environment)
dataset reuse:                  S01, S02, S06 active; S03 dormant; S04, S05 reference only
classifier reproduction:        independent re-implementation measured; not a reproduction of the papers
human comprehension evaluation: pending (guide, Label Studio config, blinded pairwise tooling shipped)
personalisation:                candidate_only
multimodal capability:          text and transcript-as-text only; image/audio/video return unsupported
```

Until the live run and the human pilot happen, this is **a working integration layer with unverified
comprehension performance**. Build on the contracts and the ontology now. Treat semantic quality as unproven.

The one measured component is a local classifier for the MaryKenneth five-class humour styles, evaluated once
on a sealed, family-grouped test of 202 texts:

| System | Macro-F1 | Accuracy |
|---|---|---|
| Majority baseline | 0.076 | 0.233 |
| Single five-class (deployed, chosen on dev) | 0.602 | 0.624 |
| Hierarchical gate + specialist | 0.615 | 0.634 |

Hierarchical minus single: +0.013, 95% CI [-0.015, 0.043], so no demonstrated gain. Details are in
`evals/reports/style-mk5-v1.md`. This classifier predicts one dataset's social-function labels and is not a
comprehension measure.

The next measured step is ready to run. `humour evaluate plan-live` prepares a bounded comparison of a plain
prompt, the ontology prompt and the full engine on identical inputs: the diagnostic pack plus 20 iSarcasmEval
sarcastic/rephrase pairs, at most 330 calls. It needs an API key and an approved spend.

## 8. Running it

```bash
pip install -e '.[dev]'
```

```bash
humour doctor
```

```bash
humour analyse -t "Excellent timing." -c "We finished moving every box an hour ago." --fixture
```

```bash
humour analyse -t "Your line here" --live          # needs ANTHROPIC_API_KEY in the environment
```

```bash
humour evaluate diagnostics --fixture
```

```bash
python3 -m pytest -q
```

Other commands: `humour compare`, `humour serve`, `humour mcp`, `humour schemas`, `humour sources audit`,
`humour evaluate style`, `humour evaluate plan-live`, `humour profile build|evaluate`,
`humour annotate export|agreement`. The full operator guide is `docs/operator_runbook.md`.

| Mode | What runs | Semantic capability |
|---|---|---|
| `live` | Anthropic Messages API with forced structured output | comprehension, compare, counterfactual, profile fit |
| `fixture` | hand-authored responses for registered inputs only | same contracts, no inference |
| `local_model` | TF-IDF + logistic regression on MaryKenneth labels | `styles` and `attribution` only |
| `heuristic` | nothing semantic ran | none |

## 9. Repository map

| Path | What lives there |
|---|---|
| `src/humour_engine/concept.py` | the stable public API for consumers |
| `src/humour_engine/contracts/` | request, result, compare, corpus and profile schemas |
| `src/humour_engine/analysis/` | context selection, prompt, validation, core, compare, rendering, retrieval |
| `src/humour_engine/models/` | provider adapters and the style classifiers |
| `src/humour_engine/{corpus,evaluation,profiles,attribution,operations,interfaces}/` | data integrity, measurement, taste profiles, LIME, budgets/runs/registry, CLI/HTTP/MCP |
| `src/humour_engine/knowledge/` | ontology, pattern cards, crosswalks: **the definition itself** |
| `schemas/` | generated JSON Schemas and `ontology.json` |
| `sources/` | provenance registry and source audit |
| `data/fixtures/` | diagnostic cases (synthetic, unreviewed) |
| `evals/` | protocols, sealed split manifest, rubrics, reports, test ledger |
| `docs/` | architecture, data card, model card, evaluation protocol, runbook, limitations |

## 10. Changing the definition

The ontology is shared infrastructure, so changes to it are deliberate:

1. Edit `src/humour_engine/knowledge/` (an axis value, a card, a crosswalk). Every new value needs a definition. Every new card
   needs positive and negative examples and stays `human_review_status: pending` until a person reviews it.
2. Run `python3 -m pytest -q`. Release validation rejects undefined values, unknown axes and cards without examples.
3. Run `humour schemas` and commit the regenerated `schemas/`.
4. Bump `CONTRACT_VERSION` in `concept.py`: minor for additions, major for renames or removals. Consumers
   pin a commit, so nothing changes under them until they upgrade.

Stylistic preferences never go through this process. If a change reads like "we prefer…" or "our brand
avoids…", it belongs in the consuming engine.
