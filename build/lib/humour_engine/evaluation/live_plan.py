"""Prepare (never execute) the first bounded live comparison: baseline prompts vs engine.

Systems on identical inputs and output budgets:
  plain     straightforward single-model prompt (no ontology, no retrieval)
  ontology  same model, explicit ontology, no retrieval
  engine    ontology + card retrieval (+ optional bounded second assessment)
Inputs: the diagnostic pack plus N iSarcasmEval sarcastic/rephrase pairs (contrastive:
the author-written rephrase should read not_supported).
Outputs a run plan with the maximum call and token counts. The plan is what gets
approved; running it needs an API key and explicit approval for the spend.
"""

from __future__ import annotations

import random
from pathlib import Path

from humour_engine.analysis.prompt import SYSTEM, build_user_message, candidate_tool_schema
from humour_engine.corpus.importers import import_isarcasm
from humour_engine.evaluation.diagnostics import case_request, load_cases
from humour_engine.operations.budget import estimate_tokens
from humour_engine.operations.registry import Registry
from humour_engine.taxonomy import load_cards, load_taxonomy

SYSTEMS = ("plain", "ontology", "engine")


def isarcasm_pairs(root: Path, n: int, seed: int = 11) -> list[dict]:
    from humour_engine.corpus.splits import assign_groups

    recs = import_isarcasm(Registry(), root, "train/train.En.csv", operation="evaluation")
    assign_groups(recs)
    by_id = {r.record_id: r for r in recs}
    pairs = [(by_id[r.parent_record_id], r) for r in recs if r.parent_record_id in by_id]
    random.Random(seed).shuffle(pairs)
    out = []
    for parent, reph in pairs[:n]:
        cats = [lab.value for lab in parent.labels if lab.value not in ("sarcastic", "not_sarcastic")]
        out.append({"family": parent.family_id, "sarcastic": parent.text_raw,
                    "rephrase": reph.text_raw, "categories": cats, "source_record": parent.record_id})
    return out


def build_plan(isarcasm_root: Path | None, n_pairs: int = 20, max_output_tokens: int = 1500, model: str = "claude-sonnet-5-5") -> dict:
    tax = load_taxonomy()
    items = []
    for c in load_cases():
        req = case_request(c, ["anthropic"], allow_external=True)
        items.append({"item": c["id"], "family": c.get("family"), "texts": [s.text for s in req.segments]})
    if isarcasm_root is not None:
        for p in isarcasm_pairs(isarcasm_root, n_pairs):
            items.append({"item": p["source_record"], "family": p["family"], "texts": [p["sarcastic"]], "expect": "supported"})
            items.append({"item": p["source_record"] + ":rephrase", "family": p["family"], "texts": [p["rephrase"]],
                          "expect": "not_supported"})
    cards = list(load_cards())[:3]
    per_call_in = []
    for it in items:
        material = {"segments": [{"segment_id": "t1", "text": " ".join(it["texts"])}]}
        per_call_in.append(estimate_tokens(SYSTEM + build_user_message(material, tax, cards) + str(candidate_tool_schema())))
    calls_per_item = {"plain": 2, "ontology": 2, "engine": 2}  # initial + one repair allowance each
    max_calls = sum(calls_per_item.values()) * len(items)
    max_in = sum(per_call_in) * sum(calls_per_item.values())
    max_out = max_calls * max_output_tokens
    return {
        "model": model,
        "systems": list(SYSTEMS),
        "n_items": len(items),
        "n_families": len({i["family"] for i in items}),
        "max_calls": max_calls,
        "max_input_tokens_estimate": max_in,
        "max_output_tokens": max_out,
        "pricing": "unknown in-repo; multiply by the provider's current per-token price before approving",
        "privacy": "item texts are sent to the Anthropic API; diagnostic texts are engine-authored, iSarcasm texts are public tweets",
        "success_signal": "engine beats plain on human-judged essential-element coverage with a paired CI excluding zero; "
                          "no rise in unsupported-claim rate or neutral false positives at matched coverage",
        "mechanical_signals": ["rephrase items read not_supported", "valid-span rate", "schema failure rate", "p50/p95 latency"],
        "items": items,
    }
