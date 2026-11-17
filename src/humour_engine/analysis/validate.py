"""Deterministic validation of a provider candidate into grounded result objects.

An interpretation that cites missing evidence, uses labels outside the ontology,
claims unobserved modalities or makes psychological claims about a person is
rejected with a visible error. It is never quietly repaired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from humour_engine.analysis.candidate import Candidate, CandidateInterpretation, QuoteRef
from humour_engine.analysis.text import SpanError, resolve_span
from humour_engine.contracts.analysis import (
    ComicReading,
    ContextBlock,
    ContextDependency,
    EngineError,
    Evidence,
    HumourAttempt,
    Interpretation,
    Modality,
    ReportedIntent,
    Segment,
    TargetSubject,
    TaskName,
    Uncertainty,
)
from humour_engine.taxonomy import Taxonomy

UNOBSERVED_MODALITY = re.compile(
    r"\b(tone of voice|vocal(ly)?|intonation|prosod\w*|facial expression|eye[- ]roll\w*|audience laugh\w*|"
    r"(he|she|they|speaker) laugh(ed|s)|deadpan delivery|pause[sd]? before|gestur\w+)\b",
    re.I,
)
PSYCH_CLAIM = re.compile(
    r"\b(narcissis\w*|depress\w*|insecur\w*|low self[- ]esteem|mental (illness|health|disorder)|"
    r"personality (disorder|trait)|psychopath\w*|sociopath\w*|self[- ]defeating (person|personality|trait)|"
    r"(is|are) (an? )?(anxious|neurotic|bitter|hostile) (person|people|individual))\b",
    re.I,
)


@dataclass
class Validated:
    comic_reading: ComicReading
    humour_attempt: HumourAttempt
    interpretations: list[Interpretation]
    evidence: list[Evidence]
    context_dependencies: list[ContextDependency]
    missing_context: list[str]
    limitations: list[str] = field(default_factory=list)
    errors: list[EngineError] = field(default_factory=list)


class EvidenceBook:
    def __init__(self, segments: dict[str, Segment]):
        self.segments = segments
        self.items: list[Evidence] = []
        self._index: dict[tuple[str, int, int], str] = {}
        self.notes: list[str] = []

    def add(self, q: QuoteRef) -> str:
        seg = self.segments.get(q.segment_id)
        if seg is None:
            raise SpanError(f"evidence cites unknown segment {q.segment_id}")
        start, end, note = resolve_span(seg.text, q.quote, q.start, q.occurrence)
        if note:
            self.notes.append(f"{q.segment_id}: {note}")
        key = (q.segment_id, start, end)
        if key in self._index:
            return self._index[key]
        eid = f"ev{len(self.items) + 1}"
        self.items.append(
            Evidence(
                evidence_id=eid,
                segment_id=q.segment_id,
                modality=seg.modality,
                start=start,
                end=end,
                exact_text=seg.text[start:end],
            )
        )
        self._index[key] = eid
        return eid


def _text_fields(ci: CandidateInterpretation) -> str:
    parts = [ci.literal_reading, ci.supported_reading or "", ci.connecting_logic or ""]
    parts += ci.expectations + ci.triggers + ci.alternatives + ci.counterevidence
    if ci.target.perspective:
        parts.append(ci.target.perspective)
    return "\n".join(parts)


def validate_candidate(
    cand: Candidate,
    segments: dict[str, Segment],
    context: ContextBlock,
    tax: Taxonomy,
    processed_modalities: set[Modality],
) -> Validated:
    errors: list[EngineError] = []
    limitations: list[str] = []
    book = EvidenceBook(segments)
    deps: list[ContextDependency] = []
    interps: list[Interpretation] = []

    def err(code: str, msg: str) -> None:
        errors.append(EngineError(code=code, message=msg, task=TaskName.comprehension))

    for ci in cand.interpretations:
        problems: list[str] = []
        # labels
        clean_labels: dict[str, list[str]] = {}
        for axis, vals in ci.labels_by_axis.items():
            if axis not in tax.axes or axis in ("comic_reading", "audience"):
                problems.append(f"unknown label axis {axis}")
                continue
            bad = [v for v in vals if v not in tax.values(axis)]
            if bad:
                problems.append(f"labels {bad} are not {axis} values")
            if not tax.is_multi(axis) and len(vals) > 1:
                problems.append(f"axis {axis} takes a single value")
            for v in vals:
                needed = tax.modality_restricted.get(v)
                if needed and not (set(needed) & {m.value for m in processed_modalities}):
                    problems.append(f"label {v} requires {needed} evidence that was not processed")
            clean_labels[axis] = list(vals)
        text = _text_fields(ci)
        if UNOBSERVED_MODALITY.search(text) and not ({Modality.audio, Modality.video} & processed_modalities):
            problems.append("claims an unobserved audio/visual observation from text-only input")
        if PSYCH_CLAIM.search(text):
            problems.append("makes a psychological or personality claim about a person")
        # evidence
        ev_ids: list[str] = []
        for q in ci.evidence:
            try:
                ev_ids.append(book.add(q))
            except SpanError as e:
                problems.append(f"invalid evidence ({q.segment_id}): {e}")
        if ci.supported_reading and not ev_ids:
            problems.append("a comic reading without any evidence span")
        # intent
        intent = None
        if ci.reported_intent is not None:
            ri = ci.reported_intent
            if ri.basis == "direct_declaration" and not (context.declared_intent and context.declared_intent_by == "speaker"):
                problems.append("claims a direct declaration of intent that was not supplied by the speaker")
            elif ri.basis == "second_hand_report" and not context.declared_intent:
                problems.append("claims a reported intent that was not supplied")
            else:
                intent = ReportedIntent(
                    whose_intent=ri.whose_intent,
                    reported_by=context.declared_intent_by or "engine",
                    basis=ri.basis,
                    statement=ri.statement,
                )
        # context claims
        claim_refs: list[str] = []
        for cc in ci.context_claims:
            status = "unverified"
            if cc.source_kind == "earlier_turn":
                if cc.source_ref in segments:
                    status = "verified_in_input"
                else:
                    problems.append(f"earlier_turn claim cites missing segment {cc.source_ref}")
                    continue
            elif cc.source_kind == "provided_fact":
                if cc.source_ref is not None and cc.source_ref.isdigit() and int(cc.source_ref) < len(context.provided_facts):
                    status = "supplied"
                else:
                    problems.append("provided_fact claim does not cite a supplied fact index")
                    continue
            elif cc.source_kind in ("visual", "acoustic"):
                wanted = Modality.image if cc.source_kind == "visual" else Modality.audio
                if wanted not in processed_modalities:
                    problems.append(f"{cc.source_kind} context claimed but that modality was not processed")
                    continue
            else:
                status = "assumed"
            did = f"ctx{len(deps) + 1}"
            deps.append(
                ContextDependency(
                    id=did,
                    claim=cc.claim,
                    source_kind=cc.source_kind,
                    source_ref=cc.source_ref,
                    required=cc.required,
                    verification_status=status,
                )
            )
            claim_refs.append(did)
        if problems:
            err("interpretation_rejected", f"{ci.id}: " + "; ".join(problems))
            continue
        interps.append(
            Interpretation(
                id=ci.id,
                literal_reading=ci.literal_reading,
                supported_reading=ci.supported_reading,
                reported_intent=intent,
                structure_kind=ci.structure_kind,
                expectations=ci.expectations,
                triggers=ci.triggers,
                connecting_logic=ci.connecting_logic,
                labels_by_axis=clean_labels,
                target_and_subject=TargetSubject(**ci.target.model_dump()),
                evidence_refs=ev_ids,
                contextual_claim_refs=claim_refs,
                counterevidence=ci.counterevidence,
                alternatives=ci.alternatives,
                uncertainty=Uncertainty(
                    score=ci.model_score,
                    score_kind="uncalibrated_model_score" if ci.model_score is not None else "unknown",
                ),
                is_main=ci.is_main,
            )
        )

    # attempt
    att_refs: list[str] = []
    for q in cand.humour_attempt.evidence:
        try:
            att_refs.append(book.add(q))
        except SpanError as e:
            err("attempt_evidence_invalid", str(e))
    att_status = cand.humour_attempt.status
    if att_status == "reported" and not context.declared_intent:
        err("attempt_not_reported", "humour attempt marked reported but no declaration was supplied; downgraded")
        att_status = "supported_inference" if att_refs else "not_established"
    attempt = HumourAttempt(status=att_status, evidence_refs=att_refs, limitations=cand.humour_attempt.limitations)

    # reading consistency
    reading = ComicReading(cand.comic_reading)
    comic = [i for i in interps if i.supported_reading]
    if reading == ComicReading.supported and not comic:
        err("reading_unsupported", "comic reading 'supported' but no grounded comic interpretation survived validation")
        reading = ComicReading.ambiguous if cand.interpretations else ComicReading.insufficient_context
        limitations.append("comic_reading downgraded because no grounded interpretation survived validation")
    if reading == ComicReading.ambiguous:
        if any(i.is_main for i in interps):
            err("ambiguous_with_main", "ambiguous reading declared a main interpretation; main flag removed")
            for i in interps:
                i.is_main = False
    if reading == ComicReading.supported and len(comic) > 1 and not any(i.is_main for i in comic):
        limitations.append("several comic readings supported; none declared main")
    limitations += book.notes
    return Validated(
        comic_reading=reading,
        humour_attempt=attempt,
        interpretations=interps,
        evidence=book.items,
        context_dependencies=deps,
        missing_context=cand.missing_context,
        limitations=limitations + cand.limitations,
        errors=errors,
    )
