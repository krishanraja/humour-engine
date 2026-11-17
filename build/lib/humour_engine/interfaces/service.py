"""Shared service layer: every interface builds dependencies and calls the core here."""

from __future__ import annotations

import os
from pathlib import Path

from humour_engine import __version__
from humour_engine.analysis.compare import compare
from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.analysis import AnalysisRequest, AnalysisResult
from humour_engine.contracts.compare import CompareRequest, CompareResult
from humour_engine.models.providers import AnthropicProvider
from humour_engine.taxonomy import load_cards, load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STYLE_MODEL = REPO_ROOT / "artifacts" / "style_model.pkl"
DEFAULT_PROFILE_DIR = REPO_ROOT / "data" / "profiles"


def build_deps(with_fixture: bool = False) -> EngineDeps:
    with_fixture = with_fixture or os.environ.get("HUMOUR_ENGINE_FIXTURE", "0") == "1"
    style = Path(os.environ.get("HUMOUR_ENGINE_STYLE_MODEL", DEFAULT_STYLE_MODEL))
    profiles = Path(os.environ.get("HUMOUR_ENGINE_PROFILE_DIR", DEFAULT_PROFILE_DIR))
    deps = EngineDeps.default(with_fixture=with_fixture, style_model_path=style, profile_dir=None)
    scope = os.environ.get("HUMOUR_ENGINE_OWNER_SCOPE")
    if scope:  # profiles are served only within one explicit owner scope
        from humour_engine.profiles.store import ProfileStore

        deps.profile_store = ProfileStore(profiles, owner_scope=scope)
    deps.second_assessment = os.environ.get("HUMOUR_ENGINE_SECOND_ASSESSMENT", "off")
    return deps


def run_analyse(payload: dict, deps: EngineDeps) -> AnalysisResult:
    return analyse(AnalysisRequest.model_validate(payload), deps)


def run_compare(payload: dict, deps: EngineDeps) -> CompareResult:
    return compare(CompareRequest.model_validate(payload), deps)


def capabilities(deps: EngineDeps) -> dict:
    providers = {
        pid: {
            "mode": p.caps.mode.value,
            "model": p.caps.model,
            "remote": p.caps.remote,
            "modalities": list(p.caps.modalities),
            "structured_output": p.caps.structured_output,
            "retention": p.caps.retention_note,
            "pricing": p.caps.pricing_source or "unknown",
        }
        for pid, p in deps.providers.items()
    }
    return {
        "engine": __version__,
        "schema_version": "1",
        "taxonomy": load_taxonomy().version,
        "modalities_supported": ["text", "transcript (as text; no acoustic evidence)"],
        "modalities_unsupported": ["image", "audio", "video"],
        "providers_configured": providers,
        "anthropic_key_present": AnthropicProvider.available(),
        "modes": {
            "live": "comprehension via an allowed remote model; requires allow_external_inference and allowlist",
            "fixture": "hand-authored responses for registered diagnostic inputs only; never for new text",
            "local_model": "styles + attribution via the local MaryKenneth-label classifier; no comprehension",
            "heuristic": "no semantic capability; returned when nothing ran",
        },
        "tasks": {
            "comprehension": "live or fixture",
            "styles": "local_model" if deps.style_model else "unavailable (no trained model loaded)",
            "attribution": "local_model" if deps.style_model else "unavailable",
            "profile_fit": "requires an explicit taste_profile_id and a completed comprehension",
            "counterfactual": "requires a supplied variant; synthetic edits not enabled",
        },
        "second_assessment": deps.second_assessment,
        "retrieval": deps.retrieval_mode,
    }


def taxonomy_payload() -> dict:
    tax = load_taxonomy()
    return {
        "version": tax.version,
        "axes": tax.axes,
        "cards": [{"id": c.id, "version": c.version, "review": c.data.get("human_review_status")} for c in load_cards()],
    }
