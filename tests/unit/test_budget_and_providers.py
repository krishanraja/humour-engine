"""Budgets, retries, malformed output, unavailable providers, fixtures (classes 15, 16, 19, 20)."""

import pytest

from humour_engine.analysis.compare import compare
from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.analysis import Budget
from humour_engine.contracts.compare import CompareRequest
from humour_engine.models.providers import AnthropicProvider, FixtureProvider, ProviderTimeout
from humour_engine.operations.budget import BudgetExceeded, BudgetLedger, PersistentBudgetStore
from tests.conftest import good_payload, make_request


def test_empty_allowlist_means_no_inference():
    req = make_request(provider_policy={"allowed_provider_ids": [], "allow_external_inference": False})
    res = analyse(req, EngineDeps.default(with_fixture=True))
    assert res.status.value == "unsupported"
    assert res.comic_reading is None
    assert res.task_results[0].errors[0].code == "no_provider_allowed"


def test_remote_provider_blocked_without_external_permission(scripted):
    p, deps = scripted(good_payload())
    req = make_request(provider_policy={"allowed_provider_ids": ["scripted"], "allow_external_inference": False})
    res = analyse(req, deps)
    assert p.calls == [] and res.status.value == "unsupported"


def test_unconfigured_anthropic_is_explicit(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    req = make_request(provider_policy={"allowed_provider_ids": ["anthropic"], "allow_external_inference": True})
    res = analyse(req, EngineDeps.default())
    assert res.task_results[0].errors[0].code == "provider_unavailable"
    assert res.comic_reading is None


def test_anthropic_adapter_parses_tool_use_without_network():
    payload = good_payload()

    def transport(body):
        assert body["tool_choice"] == {"type": "tool", "name": "submit_analysis"}
        return {"content": [{"type": "tool_use", "name": "submit_analysis", "input": payload}],
                "usage": {"input_tokens": 900, "output_tokens": 300}, "stop_reason": "tool_use"}

    prov = AnthropicProvider(model="test-model", transport=transport)
    deps = EngineDeps(providers={"anthropic": prov})
    req = make_request(provider_policy={"allowed_provider_ids": ["anthropic"], "allow_external_inference": True})
    res = analyse(req, deps)
    assert res.analysis_mode.value == "live" and res.status.value == "complete"
    assert res.usage.input_tokens == 900 and res.usage.output_tokens == 300
    assert res.usage.cost_status == "unknown"  # no verified pricing supplied


def test_malformed_output_repair_consumes_budget(scripted):
    bad = {"comic_reading": "hilarious"}
    p, deps = scripted(bad, good_payload())
    res = analyse(make_request(), deps)
    assert res.status.value == "complete"
    assert res.usage.calls == 2 and res.usage.retries == 1


def test_repair_not_attempted_when_budget_spent(scripted):
    p, deps = scripted({"comic_reading": "hilarious"}, good_payload())
    res = analyse(make_request(budget={"max_model_calls": 1}), deps)
    assert res.status.value == "failed" and len(p.calls) == 1
    assert res.task_results[0].errors[0].code == "malformed_output"


def test_two_call_budget_cannot_fund_repair_and_critic(scripted):
    uncertain = good_payload()
    uncertain["interpretations"][0]["model_score"] = 0.3  # would trigger the critic if budget allowed
    p, deps = scripted({"comic_reading": "x"}, uncertain, {"unsupported_assumptions": ["x"]})
    deps.second_assessment = "auto"
    res = analyse(make_request(budget={"max_model_calls": 2}), deps)
    assert [c["tool"] for c in p.calls] == ["submit_analysis", "submit_analysis"]
    assert len(p.payloads) == 1 and res.usage.calls == 2


def test_critic_runs_when_budget_allows_and_never_overrules(scripted):
    uncertain = good_payload()
    uncertain["interpretations"][0]["model_score"] = 0.3
    p, deps = scripted(uncertain, {"unsupported_assumptions": ["assumes a pun"], "missed_alternatives": [], "false_evidence": []})
    deps.second_assessment = "auto"
    res = analyse(make_request(budget={"max_model_calls": 2}), deps)
    assert p.calls[1]["tool"] == "submit_critique"
    assert res.comic_reading.value == "supported"  # critic adds counterevidence only
    assert any("second assessment" in c for c in res.interpretations[0].counterevidence)


def test_timeout_is_explicit_and_reservation_stands(scripted):
    p, deps = scripted(ProviderTimeout("timed out"))
    res = analyse(make_request(), deps)
    assert res.task_results[0].errors[0].code == "provider_timeout"
    assert res.task_results[0].errors[0].retryable
    assert res.usage.calls == 1


def test_strict_dollar_cap_with_unknown_pricing_stops_before_call(scripted):
    p, deps = scripted(good_payload())
    res = analyse(make_request(budget={"max_model_calls": 2, "max_cost_usd": 0.01}), deps)
    assert p.calls == []
    assert res.task_results[0].errors[0].code == "budget_exhausted"


def test_ledger_limits():
    led = BudgetLedger(budget=Budget(max_model_calls=1, max_input_tokens=100, max_output_tokens=10))
    led.reserve(50, 10)
    with pytest.raises(BudgetExceeded):
        led.reserve(10, 10)


def test_restart_preserves_consumed_budget(tmp_path):
    store = PersistentBudgetStore(tmp_path / "b.sqlite")
    b = Budget(max_model_calls=3)
    led = store.load("run1", b)
    led.reserve(10, 10)
    led.reserve(10, 10)
    store.save("run1", led)
    again = PersistentBudgetStore(tmp_path / "b.sqlite").load("run1", b)
    assert again.calls == 2 and again.remaining_calls() == 1
    with pytest.raises(ValueError):
        store.load("run1", Budget(max_model_calls=10))  # cannot reset allowance by changing budget


def test_fixture_never_answers_new_text():
    deps = EngineDeps(providers={"fixture": FixtureProvider()})
    req = make_request(text="An unregistered sentence.", provider_policy={"allowed_provider_ids": ["fixture"]})
    res = analyse(req, deps)
    assert res.analysis_mode.value == "fixture"
    assert res.comic_reading is None
    assert res.task_results[0].errors[0].code == "fixture_missing"


def test_fixture_output_is_always_labelled():
    deps = EngineDeps(providers={"fixture": FixtureProvider()})
    req = make_request(provider_policy={"allowed_provider_ids": ["fixture"]})
    res = analyse(req, deps)
    assert res.analysis_mode.value == "fixture"
    assert res.limitations[0].startswith("FIXTURE MODE")
    from humour_engine.analysis.render import render_markdown

    assert "FIXTURE MODE" in render_markdown(res)


def test_compare_shares_one_budget(scripted):
    p, deps = scripted(good_payload(), good_payload())
    seg = [{"segment_id": "t1", "text": "The bank promised interest. I am still bored.", "sequence": 1}]
    seg2 = [{"segment_id": "t1", "text": "The bank promised interest. The rate is fixed.", "sequence": 1}]
    creq = CompareRequest.model_validate({
        "request_id": "c", "focus_segment_ids": ["t1"],
        "variant_a": {"label": "a", "segments": seg}, "variant_b": {"label": "b", "segments": seg2},
        "provider_policy": {"allowed_provider_ids": ["scripted"], "allow_external_inference": True},
        "budget": {"max_model_calls": 1}})
    res = compare(creq, deps)
    assert len(p.calls) == 1
    assert res.status == "partial"
    assert res.analysis_b.task_results[0].errors[0].code == "budget_exhausted"
