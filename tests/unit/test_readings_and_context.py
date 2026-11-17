"""Literal/ambiguous handling, missing context, truncation, callbacks (classes 4, 12)."""

from humour_engine.analysis.context import select_context
from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.analysis import AnalysisRequest
from tests.conftest import good_payload, make_request


def test_not_supported_is_a_normal_answer(scripted):
    pl = good_payload(reading="not_supported")
    p, deps = scripted(pl)
    res = analyse(make_request(), deps)
    assert res.status.value == "complete"
    assert res.comic_reading.value == "not_supported"
    assert not any(i.is_main for i in res.interpretations)


def test_supported_without_grounded_comic_reading_is_downgraded(scripted):
    pl = good_payload(reading="not_supported")
    pl["comic_reading"] = "supported"
    p, deps = scripted(pl)
    res = analyse(make_request(), deps)
    assert res.comic_reading.value != "supported"
    assert any(e.code == "reading_unsupported" for e in res.errors)


def test_ambiguous_drops_main_flag_visibly(scripted):
    pl = good_payload()
    pl["comic_reading"] = "ambiguous"
    p, deps = scripted(pl)
    res = analyse(make_request(), deps)
    assert not any(i.is_main for i in res.interpretations)
    assert any(e.code == "ambiguous_with_main" for e in res.errors)


def _long_request(n_prior=5, prior_len=3000):
    segs = [{"segment_id": f"p{i}", "text": "x" * prior_len, "sequence": i} for i in range(n_prior)]
    segs.append({"segment_id": "t1", "text": "Excellent timing.", "sequence": n_prior})
    return AnalysisRequest.model_validate(
        {"request_id": "r", "focus_segment_ids": ["t1"], "segments": segs,
         "provider_policy": {"allowed_provider_ids": ["scripted"], "allow_external_inference": True}}
    )


def test_truncation_is_reported_and_abstains_when_setup_may_be_lost(scripted):
    req = _long_request()
    sel = select_context(req, max_chars=7000)
    assert sel.truncation.occurred and sel.truncation.potentially_lost_payoff
    p, deps = scripted(good_payload(quote="Excellent"))
    deps.max_input_chars = 7000
    res = analyse(req, deps)
    assert res.truncation.occurred
    assert res.task_results[0].status.value == "abstained"
    assert res.comic_reading is None
    assert p.calls == []  # no model call on a fragment


def test_oversized_focus_abstains():
    req = make_request(text="y" * 5000)
    res = analyse(req, EngineDeps(max_input_chars=1000))
    assert res.task_results[0].status.value == "abstained"


def test_callback_cites_antecedent_turn(scripted):
    pl = good_payload(quote="manager", seg="t2")
    pl["interpretations"][0]["labels_by_axis"] = {"mechanism": ["callback"]}
    pl["interpretations"][0]["context_claims"] = [
        {"claim": "printer nicknamed manager", "source_kind": "earlier_turn", "source_ref": "t0", "required": True}
    ]
    p, deps = scripted(pl)
    req = AnalysisRequest.model_validate({
        "request_id": "r", "focus_segment_ids": ["t2"],
        "segments": [{"segment_id": "t0", "text": "The printer is the real manager.", "sequence": 0},
                     {"segment_id": "t2", "text": "I'll ask the manager for paper.", "sequence": 2}],
        "provider_policy": {"allowed_provider_ids": ["scripted"], "allow_external_inference": True}})
    res = analyse(req, deps)
    assert res.context_dependencies[0].verification_status == "verified_in_input"


def test_callback_to_missing_antecedent_rejected(scripted):
    pl = good_payload(quote="manager")
    pl["interpretations"][0]["context_claims"] = [
        {"claim": "printer nicknamed manager", "source_kind": "earlier_turn", "source_ref": "t0", "required": True}
    ]
    p, deps = scripted(pl)
    res = analyse(make_request(text="I'll ask the manager for paper."), deps)
    assert res.status.value == "failed"
