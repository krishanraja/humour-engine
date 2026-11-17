from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from humour_engine.analysis.core import EngineDeps
from humour_engine.contracts.analysis import AnalysisMode, AnalysisRequest
from humour_engine.models.providers import ProviderCapabilities, ProviderResponse, ProviderUnavailable

SRC = Path(os.environ.get("HUMOUR_ENGINE_SOURCES", "/tmp/claude-0/-home-user/2d2bb0e5-d241-5b37-a77f-5e9ddc94c69d/scratchpad/src"))


class ScriptedProvider:
    """Test double that returns queued payloads and counts calls. Declares itself live+remote
    so policy gates are exercised exactly as for a real external provider."""

    def __init__(self, payloads, remote=True, provider_id="scripted"):
        self.payloads = list(payloads)
        self.calls = []
        self.caps = ProviderCapabilities(
            provider_id=provider_id, model="scripted-1", mode=AnalysisMode.live, modalities=("text",),
            structured_output="test", max_context_tokens=100000, max_output_tokens=500, timeout_s=1,
            max_retries=0, remote=remote, retention_note="test",
        )

    def interpret(self, system, user, tool, max_output_tokens):
        self.calls.append({"system": system, "user": user, "tool": tool["name"]})
        if not self.payloads:
            raise ProviderUnavailable("exhausted", "no scripted payload left")
        p = self.payloads.pop(0)
        if isinstance(p, Exception):
            raise p
        return ProviderResponse(payload=copy.deepcopy(p), input_tokens=100, output_tokens=50)


def make_request(text="The bank promised interest. I am still bored.", tasks=("comprehension",), **kw) -> AnalysisRequest:
    payload = {
        "request_id": "r1",
        "focus_segment_ids": ["t1"],
        "segments": [{"segment_id": "t1", "speaker_id": "a", "text": text, "sequence": 1}],
        "tasks": list(tasks),
        "provider_policy": {"allowed_provider_ids": ["scripted"], "allow_external_inference": True},
    }
    payload.update(kw)
    return AnalysisRequest.model_validate(payload)


def good_payload(quote="interest", seg="t1", reading="supported"):
    return {
        "comic_reading": reading,
        "humour_attempt": {"status": "supported_inference", "evidence": [{"segment_id": seg, "quote": quote}]},
        "interpretations": [
            {
                "id": "i1",
                "is_main": reading == "supported",
                "literal_reading": "literal",
                "supported_reading": "comic" if reading == "supported" else None,
                "connecting_logic": "two senses of interest",
                "labels_by_axis": {"mechanism": ["ambiguity"]},
                "evidence": [{"segment_id": seg, "quote": quote}],
                "model_score": 0.8,
            }
        ],
        "missing_context": [],
    }


@pytest.fixture
def scripted():
    def _make(*payloads, remote=True):
        p = ScriptedProvider(payloads, remote=remote)
        return p, EngineDeps(providers={"scripted": p})

    return _make


@pytest.fixture
def sources_root():
    if not (SRC / "Two_Model_Humour_Style").exists():
        pytest.skip("upstream source checkouts not present")
    return SRC
