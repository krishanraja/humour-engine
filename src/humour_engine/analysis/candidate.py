"""The structured shape a provider must return. Validated strictly before any use."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from humour_engine.contracts.base import Strict

PROMPT_VERSION = "comprehension-v1"


class QuoteRef(Strict):
    segment_id: str
    quote: str = Field(min_length=1)
    start: int | None = Field(default=None, ge=0)
    occurrence: int | None = Field(default=None, ge=0)


class ContextClaim(Strict):
    claim: str
    source_kind: Literal[
        "linguistic", "topical", "cultural", "interpersonal", "earlier_turn", "visual", "acoustic", "provided_fact"
    ]
    source_ref: str | None = None
    required: bool = False


class CandidateTarget(Strict):
    subject: str | None = None
    target: Literal[
        "self", "other_person", "behaviour", "situation", "institution", "convention", "fictional_person", "none", "unknown"
    ] = "unknown"
    perspective: str | None = None


class CandidateIntent(Strict):
    whose_intent: str
    basis: Literal["direct_declaration", "second_hand_report", "inference"]
    statement: str


class CandidateInterpretation(Strict):
    id: str
    literal_reading: str
    supported_reading: str | None = None
    reported_intent: CandidateIntent | None = None
    structure_kind: str | None = None
    expectations: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    connecting_logic: str | None = None
    labels_by_axis: dict[str, list[str]] = Field(default_factory=dict)
    target: CandidateTarget = Field(default_factory=CandidateTarget)
    evidence: list[QuoteRef] = Field(default_factory=list)
    context_claims: list[ContextClaim] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    model_score: float | None = Field(default=None, ge=0, le=1)
    is_main: bool = False


class CandidateAttempt(Strict):
    status: Literal["reported", "supported_inference", "not_established"]
    evidence: list[QuoteRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Candidate(Strict):
    comic_reading: Literal["supported", "not_supported", "ambiguous", "insufficient_context"]
    humour_attempt: CandidateAttempt
    interpretations: list[CandidateInterpretation] = Field(default_factory=list, max_length=6)
    missing_context: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Critique(Strict):
    unsupported_assumptions: list[str] = Field(default_factory=list)
    missed_alternatives: list[str] = Field(default_factory=list)
    false_evidence: list[str] = Field(default_factory=list)
