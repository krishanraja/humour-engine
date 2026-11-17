"""Schema/version compatibility and completion invariants (test classes 1, 20)."""

import pytest
from pydantic import ValidationError

from humour_engine.contracts.analysis import AnalysisRequest, AnalysisResult, Uncertainty
from tests.conftest import make_request


def test_unknown_schema_version_rejected():
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate({**make_request().model_dump(mode="json"), "schema_version": "2"})


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate({**make_request().model_dump(mode="json"), "surprise": 1})


def test_duplicate_segment_ids_across_context_rejected():
    with pytest.raises(ValidationError, match="unique"):
        make_request(context={"prior_segments": [{"segment_id": "t1", "text": "x", "sequence": 0}]})


def test_focus_must_exist():
    with pytest.raises(ValidationError, match="focus_segment_ids"):
        make_request(focus_segment_ids=["nope"])


def test_sequence_order_enforced():
    with pytest.raises(ValidationError, match="sequence"):
        AnalysisRequest.model_validate(
            {"request_id": "r", "focus_segment_ids": ["a"],
             "segments": [{"segment_id": "a", "text": "x", "sequence": 2}, {"segment_id": "b", "text": "y", "sequence": 1}]}
        )


def test_unknown_confidence_is_null_not_zero():
    with pytest.raises(ValidationError):
        Uncertainty(score=0.0, score_kind="unknown")
    assert Uncertainty().score is None


def test_calibrated_probability_needs_reference():
    with pytest.raises(ValidationError):
        Uncertainty(score=0.7, score_kind="calibrated_probability")


def _result(**kw):
    base = dict(
        analysis_id="a", request_id="r", input_revision="rev", versions={"engine": "0", "taxonomy": "t"},
        analysis_mode="fixture", requested_tasks=["comprehension"],
        task_results=[{"task": "comprehension", "status": "complete"}], status="complete",
    )
    base.update(kw)
    return AnalysisResult.model_validate(base)


def test_complete_requires_every_task_complete():
    with pytest.raises(ValidationError, match="complete"):
        _result(requested_tasks=["comprehension", "styles"],
                task_results=[{"task": "comprehension", "status": "complete"}, {"task": "styles", "status": "unsupported"}])


def test_failed_result_cannot_carry_semantic_verdict():
    with pytest.raises(ValidationError):
        _result(task_results=[{"task": "comprehension", "status": "failed"}], status="failed", comic_reading="supported")


def test_dangling_evidence_reference_rejected():
    with pytest.raises(ValidationError, match="unknown evidence"):
        _result(comic_reading="supported",
                interpretations=[{"id": "i1", "literal_reading": "x", "evidence_refs": ["ev9"]}])


def test_ambiguous_cannot_have_main():
    with pytest.raises(ValidationError, match="ambiguous"):
        _result(comic_reading="ambiguous", interpretations=[{"id": "i1", "literal_reading": "x", "is_main": True}])


def test_mode_survives_roundtrip():
    r = _result()
    again = AnalysisResult.model_validate_json(r.model_dump_json())
    assert again.analysis_mode.value == "fixture"
