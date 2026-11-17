"""Result cache used only under explicit retention. Keys carry every version and the privacy scope."""

from __future__ import annotations

import json

from humour_engine.analysis.candidate import PROMPT_VERSION
from humour_engine.analysis.text import sha
from humour_engine.contracts.analysis import AnalysisResult
from humour_engine.taxonomy import cards_snapshot, load_taxonomy


class ResultCache:
    def __init__(self, scope: str):
        if not scope:
            raise ValueError("cache scope (tenant/user) is required")
        self.scope = scope
        self._store: dict[str, str] = {}

    def key(self, req, rev: str, deps) -> str:
        providers = sorted(f"{k}:{p.caps.model}" for k, p in deps.providers.items() if k in req.provider_policy.allowed_provider_ids)
        parts = {
            "scope": self.scope,
            "rev": rev,
            "tasks": [t.value for t in req.tasks],
            "providers": providers,
            "external": req.provider_policy.allow_external_inference,
            "prompt": PROMPT_VERSION,
            "taxonomy": load_taxonomy().version,
            "retrieval": f"{deps.retrieval_mode}:{cards_snapshot()}",
            "profile": req.taste_profile_id,
            "profile_version": deps.profile_store.version_of(req.taste_profile_id)
            if (deps.profile_store and req.taste_profile_id)
            else None,
            "style_model": getattr(deps.style_model, "model_id", None),
            "prompt_variant": deps.prompt_variant,
            "second_assessment": deps.second_assessment,
            "max_input_chars": deps.max_input_chars,
            "max_calls_per_request": deps.max_calls_per_request,
            "budget": req.budget.model_dump(mode="json"),
            "request_id": req.request_id,
        }
        return sha(json.dumps(parts, sort_keys=True))

    def get(self, key: str) -> AnalysisResult | None:
        raw = self._store.get(key)
        return AnalysisResult.model_validate_json(raw) if raw else None

    def put(self, key: str, res: AnalysisResult) -> None:
        self._store[key] = res.model_dump_json()
