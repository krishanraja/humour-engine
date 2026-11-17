"""Control Center provider: engine bearer route, Control Center's key and model, explicit failures."""

import json
from pathlib import Path

import pytest

from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.concept import prompt_hashes
from humour_engine.models.providers import ControlCenterProvider, ProviderUnavailable
from tests.conftest import good_payload, make_request

ROOT = Path(__file__).resolve().parents[2]


def _req():
    return make_request(provider_policy={"allowed_provider_ids": ["controlcenter"], "allow_external_inference": True})


def test_route_body_and_usage(monkeypatch):
    monkeypatch.setenv("HUMOUR_ENGINE_CC_ENGINE", "growth-heartside")
    seen = {}

    def transport(url, body):
        seen.update(url=url, body=body)
        return 200, {"ok": True, "payload": good_payload(), "model": "claude-sonnet-5", "prompt": "comprehension-v1:engine",
                     "usage": {"input_tokens": 1200, "output_tokens": 300}, "cost_usd": 0.0054, "cap": 200, "used": 1}

    deps = EngineDeps(providers={"controlcenter": ControlCenterProvider(transport=transport)})
    res = analyse(_req(), deps)
    assert seen["url"] == "https://controlcenter.krishraja.com/api/growth/engines/growth-heartside/humour"
    assert seen["body"]["tool"]["name"] == "submit_analysis"
    assert set(seen["body"]) == {"system", "user", "tool", "max_output_tokens"}  # never a model or a key
    assert res.status.value == "complete" and res.analysis_mode.value == "live"
    assert res.usage.input_tokens == 1200 and res.usage.output_tokens == 300


def test_refusals_are_explicit(monkeypatch):
    monkeypatch.setenv("HUMOUR_ENGINE_CC_ENGINE", "growth-heartside")
    for status, err in [(403, "unknown_prompt: x"), (429, "daily_humour_cap_reached"), (503, "missing_anthropic_key")]:
        prov = ControlCenterProvider(transport=lambda url, body, s=status, e=err: (s, {"ok": False, "error": e}))
        res = analyse(_req(), EngineDeps(providers={"controlcenter": prov}))
        assert res.comic_reading is None
        assert res.task_results[0].errors[0].code.startswith("controlcenter_")


def test_unconfigured_is_unavailable(monkeypatch):
    monkeypatch.delenv("HUMOUR_ENGINE_CC_ENGINE", raising=False)
    with pytest.raises(ProviderUnavailable):
        ControlCenterProvider(transport=lambda u, b: (200, {})).interpret("s", "u", {"name": "submit_analysis"}, 100)
    assert not ControlCenterProvider.available()


def test_published_prompt_hashes_are_current():
    committed = json.loads((ROOT / "schemas" / "prompt_hashes.json").read_text())["prompts"]
    assert committed == prompt_hashes(), "prompt changed: run `humour schemas` and add the new hash to control-center HUMOUR_PROMPTS"
