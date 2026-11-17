"""Stable public API for repositories that consume humour-engine as their definition of humour.

Consumers import from here (or read the exported JSON Schemas in `schemas/`) rather than
reaching into internal modules. Anything exported here follows CONTRACT_VERSION:
additive changes bump the minor number, breaking changes bump the major number.

Boundary: this package defines and understands humour. It does not decide what any
product should sound like. Style preferences belong to the consuming engine, expressed
either in its own logic or as an explicit TasteProfile passed to `profile_fit`.
"""

from __future__ import annotations

import json
from pathlib import Path

from humour_engine.analysis.compare import compare
from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.analysis.render import render_markdown
from humour_engine.contracts.analysis import AnalysisRequest, AnalysisResult
from humour_engine.contracts.compare import CompareRequest, CompareResult
from humour_engine.contracts.profile import FeedbackItem, PairwisePreference, TasteProfile
from humour_engine.taxonomy import load_cards, load_crosswalk, load_taxonomy

CONTRACT_VERSION = "1.0"

__all__ = [
    "CONTRACT_VERSION",
    "AnalysisRequest",
    "AnalysisResult",
    "CompareRequest",
    "CompareResult",
    "TasteProfile",
    "FeedbackItem",
    "PairwisePreference",
    "EngineDeps",
    "analyse",
    "compare",
    "render_markdown",
    "ontology",
    "define",
    "pattern_cards",
    "crosswalk",
    "export_schemas",
]


def ontology() -> dict:
    """Every axis with its description, whether it takes several values, and each value's definition."""
    tax = load_taxonomy()
    out = {"version": tax.version, "axes": {}}
    for axis, spec in tax.axes.items():
        vals = spec["values"]
        out["axes"][axis] = {
            "description": spec.get("description"),
            "multi": bool(spec.get("multi")),
            "values": vals if isinstance(vals, dict) else {v: None for v in vals},
        }
    out["modality_restricted"] = tax.modality_restricted
    return out


def define(axis: str, value: str) -> str | None:
    """Definition of one ontology value, e.g. define("mechanism", "callback")."""
    vals = load_taxonomy().axes[axis]["values"]
    if isinstance(vals, dict):
        if value not in vals:
            raise KeyError(f"{value} is not a {axis} value")
        return vals[value]
    if value not in vals:
        raise KeyError(f"{value} is not a {axis} value")
    return None


def pattern_cards() -> list[dict]:
    """Pattern cards with required evidence, insufficient evidence and examples (review status included)."""
    return [dict(c.data) for c in load_cards()]


def crosswalk(name: str) -> dict:
    """Label crosswalk, e.g. crosswalk("mk5_to_engine")."""
    return load_crosswalk(name)


SCHEMA_MODELS = {
    "analysis_request": AnalysisRequest,
    "analysis_result": AnalysisResult,
    "compare_request": CompareRequest,
    "compare_result": CompareResult,
    "taste_profile": TasteProfile,
    "feedback_item": FeedbackItem,
    "pairwise_preference": PairwisePreference,
}


def export_schemas(out_dir: Path) -> list[Path]:
    """Write JSON Schemas for every public contract plus the ontology, for non-Python consumers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema()
        schema["$id"] = f"humour-engine/{CONTRACT_VERSION}/{name}.schema.json"
        p = out_dir / f"{name}.schema.json"
        p.write_text(json.dumps(schema, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        paths.append(p)
    p = out_dir / "ontology.json"
    p.write_text(json.dumps({"contract_version": CONTRACT_VERSION, **ontology()}, indent=1, sort_keys=True,
                            ensure_ascii=False) + "\n")
    paths.append(p)
    return paths
