"""Profiles, counterfactuals, attribution and partial results."""

from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.profile import FeedbackItem
from humour_engine.models.providers import FixtureProvider
from humour_engine.models.style import StyleModel
from humour_engine.profiles.build import build_candidate
from humour_engine.profiles.evaluate import evaluate_profile
from humour_engine.profiles.store import ProfileStore
from tests.conftest import make_request
from tests.unit.test_style_models import LABELS, TEXTS


def _items():
    return [
        FeedbackItem(item_id="a1", text="x", judgement="approved", labels_by_axis={"mechanism": ["ambiguity"]}),
        FeedbackItem(item_id="a2", text="y", judgement="approved", labels_by_axis={"mechanism": ["ambiguity"]}),
        FeedbackItem(item_id="r1", text="z", judgement="rejected", labels_by_axis={"mechanism": ["exaggeration"]}),
    ]


def test_single_rejection_is_not_a_rule():
    prof = build_candidate("p", "u", _items())
    assert [(p.axis, p.value, p.direction) for p in prof.preferences] == [("mechanism", "ambiguity", "prefer")]
    assert prof.approval_state == "candidate"


def test_conflicts_are_kept_not_resolved():
    items = _items() + [FeedbackItem(item_id="r2", text="w", judgement="rejected", labels_by_axis={"mechanism": ["ambiguity"]})]
    prof = build_candidate("p", "u", items)
    assert prof.unresolved_conflicts and not prof.preferences


def test_profile_fit_is_separate_from_reading(tmp_path):
    store = ProfileStore(tmp_path)
    store.save_candidate(build_candidate("p1", "u", _items()))
    deps = EngineDeps(providers={"fixture": FixtureProvider()}, profile_store=store)
    req = make_request(tasks=["comprehension", "profile_fit"], taste_profile_id="p1",
                       provider_policy={"allowed_provider_ids": ["fixture"]})
    res = analyse(req, deps)
    assert res.comic_reading.value == "supported"
    assert res.audience_assessment.fit == "match"
    assert res.audience_assessment.score_kind == "descriptive_rule_fit"


def test_missing_profile_is_unsupported_but_comprehension_survives(tmp_path):
    deps = EngineDeps(providers={"fixture": FixtureProvider()}, profile_store=ProfileStore(tmp_path))
    req = make_request(tasks=["comprehension", "profile_fit"], taste_profile_id="nope",
                       provider_policy={"allowed_provider_ids": ["fixture"]})
    res = analyse(req, deps)
    assert res.status.value == "partial"
    assert res.comic_reading is not None
    assert [t.status.value for t in res.task_results] == ["complete", "unsupported"]


def test_profile_evaluation_needs_withheld_feedback():
    assert evaluate_profile(_items())["status"] == "insufficient_feedback"
    many = [FeedbackItem(item_id=f"i{n}", text="t", judgement="approved" if n % 2 else "rejected",
                         labels_by_axis={"mechanism": ["ambiguity" if n % 2 else "exaggeration"]},
                         recorded_at=f"2026-01-{n + 1:02d}") for n in range(20)]
    r = evaluate_profile(many)
    assert r["status"] == "measured" and r["holdout"] == "temporal"
    assert r["n_train"] + r["n_heldout"] == 20


def test_counterfactual_observes_change_with_both_ids():
    deps = EngineDeps(providers={"fixture": FixtureProvider()})
    req = make_request(tasks=["comprehension", "counterfactual"],
                       counterfactual_variant=[{"segment_id": "t1", "sequence": 1, "speaker_id": "a",
                                                "text": "The bank promised interest. The branch opens at nine."}],
                       provider_policy={"allowed_provider_ids": ["fixture"]}, budget={"max_model_calls": 2})
    res = analyse(req, deps)
    cf = res.counterfactual_analysis
    assert cf.variant_analysis_id and cf.original_input_revision != cf.variant_input_revision
    assert "supported -> not_supported" in cf.observed_change
    assert cf.human_validated is False


def test_counterfactual_without_budget_leaves_observed_null():
    deps = EngineDeps(providers={"fixture": FixtureProvider()})
    req = make_request(tasks=["comprehension", "counterfactual"],
                       counterfactual_variant=[{"segment_id": "t1", "sequence": 1, "text": "Plain text."}],
                       provider_policy={"allowed_provider_ids": ["fixture"]}, budget={"max_model_calls": 1})
    res = analyse(req, deps)
    assert res.counterfactual_analysis.observed_change is None
    assert res.status.value == "partial"


def test_styles_and_attribution_on_local_model():
    m = StyleModel(variant="hierarchical", C=1.0).fit(TEXTS, LABELS)
    deps = EngineDeps(style_model=m)
    res = analyse(make_request(tasks=["styles", "attribution"]), deps)
    assert res.analysis_mode.value == "local_model"
    assert res.comic_reading is None  # a style label is not comprehension
    a = res.attributions[0]
    assert a.method == "lime_text_word_removal" and a.settings["seed"] == 0
    assert a.prediction == res.style_prediction.predicted  # explains the full composed path's output


def test_attribution_unsupported_without_queryable_model():
    res = analyse(make_request(tasks=["attribution"]), EngineDeps())
    assert res.status.value == "unsupported"
