"""Evidence grounding, Unicode offsets, modality/personality/intent guards (classes 2, 3, 5)."""

import pytest

from humour_engine.analysis.core import analyse
from humour_engine.analysis.text import SpanError, codepoint_to_utf16, resolve_span, utf16_to_codepoint
from tests.conftest import good_payload, make_request


def test_valid_span_offsets_are_codepoints():
    text = "Monday 🙃 my favourite day, said nobody."
    s, e, _ = resolve_span(text, "said nobody")
    assert text[s:e] == "said nobody"
    # the emoji is one code point but two UTF-16 units
    assert codepoint_to_utf16(text, s) == s + 1
    assert utf16_to_codepoint(text, codepoint_to_utf16(text, s)) == s


def test_combining_and_non_latin_text():
    text = "Café 没问题 नमस्ते"
    s, e, _ = resolve_span(text, "没问题")
    assert text[s:e] == "没问题"
    assert utf16_to_codepoint(text, codepoint_to_utf16(text, e)) == e


def test_utf16_offset_inside_surrogate_pair_rejected():
    with pytest.raises(ValueError):
        utf16_to_codepoint("a🙃b", 2)


def test_wrong_start_offset_rejected():
    with pytest.raises(SpanError):
        resolve_span("abc def", "def", start=0)


def test_normalised_quote_is_not_accepted():
    with pytest.raises(SpanError):
        resolve_span("It’s fine", "It's fine")  # curly vs straight apostrophe


def test_fabricated_quote_fails_visibly(scripted):
    p, deps = scripted(good_payload(quote="money"))
    res = analyse(make_request(), deps)
    assert res.comic_reading is None
    assert res.task_results[0].status.value == "failed"
    assert any("not found verbatim" in e.message for e in res.errors)


def test_evidence_in_unknown_segment_fails(scripted):
    p, deps = scripted(good_payload(seg="t9"))
    res = analyse(make_request(), deps)
    assert res.status.value == "failed"


def test_valid_evidence_resolves(scripted):
    p, deps = scripted(good_payload())
    res = analyse(make_request(), deps)
    assert res.status.value == "complete"
    ev = res.evidence[0]
    seg_text = make_request().segments[0].text
    assert seg_text[ev.start:ev.end] == ev.exact_text == "interest"
    assert res.interpretations[0].evidence_refs == [ev.evidence_id]


def test_audio_claim_from_text_rejected(scripted):
    pl = good_payload()
    pl["interpretations"][0]["connecting_logic"] = "The deadpan delivery and the pause before 'bored' sell it."
    p, deps = scripted(pl)
    res = analyse(make_request(), deps)
    assert res.status.value == "failed"
    assert any("unobserved audio" in e.message for e in res.errors)


def test_acoustic_label_requires_audio(scripted):
    pl = good_payload()
    pl["interpretations"][0]["labels_by_axis"]["register"] = ["acoustically_deadpan"]
    p, deps = scripted(pl)
    assert analyse(make_request(), deps).status.value == "failed"


def test_personality_claim_rejected(scripted):
    pl = good_payload()
    pl["interpretations"][0]["supported_reading"] = "The speaker is clearly depressed and insecure."
    p, deps = scripted(pl)
    res = analyse(make_request(), deps)
    assert any("psychological" in e.message for e in res.errors)


def test_label_outside_ontology_rejected(scripted):
    pl = good_payload()
    pl["interpretations"][0]["labels_by_axis"]["mechanism"] = ["hilarity"]
    p, deps = scripted(pl)
    assert analyse(make_request(), deps).status.value == "failed"


def test_invented_direct_declaration_of_intent_rejected(scripted):
    pl = good_payload()
    pl["interpretations"][0]["reported_intent"] = {"whose_intent": "a", "basis": "direct_declaration", "statement": "joking"}
    p, deps = scripted(pl)
    assert analyse(make_request(), deps).status.value == "failed"


def test_caller_report_is_not_a_speaker_declaration(scripted):
    pl = good_payload()
    pl["interpretations"][0]["reported_intent"] = {"whose_intent": "a", "basis": "direct_declaration", "statement": "joking"}
    p, deps = scripted(pl)
    req = make_request(context={"declared_intent": "a was joking", "declared_intent_by": "caller"})
    assert analyse(req, deps).status.value == "failed"


def test_reported_attempt_without_declaration_is_downgraded(scripted):
    pl = good_payload()
    pl["humour_attempt"]["status"] = "reported"
    p, deps = scripted(pl)
    res = analyse(make_request(), deps)
    assert res.humour_attempt.status == "supported_inference"
    assert any(e.code == "attempt_not_reported" for e in res.errors)
