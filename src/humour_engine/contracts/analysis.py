"""Analysis request and result contracts (schema version 1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from humour_engine.contracts.base import Strict

SCHEMA_VERSION = "1"

MAX_SEGMENTS = 64
MAX_SEGMENT_CHARS = 8000


class Modality(StrEnum):
    text = "text"
    transcript = "transcript"
    image = "image"
    audio = "audio"
    video = "video"


SUPPORTED_MODALITIES = {Modality.text, Modality.transcript}


class TaskName(StrEnum):
    comprehension = "comprehension"
    styles = "styles"
    counterfactual = "counterfactual"
    profile_fit = "profile_fit"
    attribution = "attribution"


class Segment(Strict):
    segment_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    speaker_id: str | None = Field(default=None, max_length=128)
    text: str = Field(max_length=MAX_SEGMENT_CHARS)
    modality: Modality = Modality.text
    sequence: int = Field(ge=0)
    quoted_from: str | None = Field(
        default=None, description="Speaker ID of a quoted voice when this segment reports someone else's words."
    )


class ContextBlock(Strict):
    provided_facts: list[str] = Field(default_factory=list, max_length=64)
    prior_segments: list[Segment] = Field(default_factory=list, max_length=MAX_SEGMENTS)
    audience_description: str | None = None
    known_references: list[str] = Field(default_factory=list, max_length=64)
    locale: str | None = None
    declared_intent: str | None = Field(
        default=None, description="A caller-supplied statement of intent. Stored as a report with provenance."
    )
    declared_intent_by: Literal["speaker", "caller", "third_party"] | None = None


class ProviderPolicy(Strict):
    allowed_provider_ids: list[str] = Field(default_factory=list)
    allow_external_inference: bool = False


class Budget(Strict):
    max_model_calls: int = Field(default=2, ge=0, le=20)
    max_input_tokens: int = Field(default=8000, ge=0)
    max_output_tokens: int = Field(default=2000, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)


class AnalysisRequest(Strict):
    schema_version: Literal["1"] = SCHEMA_VERSION
    request_id: str = Field(min_length=1, max_length=128)
    language: str = "en"
    focus_segment_ids: list[str] = Field(min_length=1)
    segments: list[Segment] = Field(min_length=1, max_length=MAX_SEGMENTS)
    context: ContextBlock = Field(default_factory=ContextBlock)
    tasks: list[TaskName] = Field(default_factory=lambda: [TaskName.comprehension])
    taste_profile_id: str | None = None
    privacy_mode: Literal["ephemeral", "retain"] = "ephemeral"
    provider_policy: ProviderPolicy = Field(default_factory=ProviderPolicy)
    budget: Budget = Field(default_factory=Budget)
    counterfactual_variant: list[Segment] | None = Field(
        default=None, description="Optional supplied minimal edit of the focus segments for the counterfactual task."
    )

    @model_validator(mode="after")
    def _ids_consistent(self) -> AnalysisRequest:
        ids = [s.segment_id for s in self.segments] + [s.segment_id for s in self.context.prior_segments]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"segment ids must be unique across segments and context: {sorted(dupes)}")
        own = {s.segment_id for s in self.segments}
        missing = [f for f in self.focus_segment_ids if f not in own]
        if missing:
            raise ValueError(f"focus_segment_ids not present in segments: {missing}")
        seqs = [s.sequence for s in self.segments]
        if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
            raise ValueError("segments must be in strictly increasing sequence order")
        if len(set(self.tasks)) != len(self.tasks):
            raise ValueError("tasks must not repeat")
        return self

    def all_segments(self) -> dict[str, Segment]:
        out = {s.segment_id: s for s in self.context.prior_segments}
        out.update({s.segment_id: s for s in self.segments})
        return out


# ---------------------------------------------------------------- results


class AnalysisMode(StrEnum):
    live = "live"
    local_model = "local_model"
    heuristic = "heuristic"
    fixture = "fixture"


class ResultStatus(StrEnum):
    complete = "complete"
    partial = "partial"
    abstained = "abstained"
    unsupported = "unsupported"
    failed = "failed"


class TaskStatus(StrEnum):
    complete = "complete"
    abstained = "abstained"
    unsupported = "unsupported"
    failed = "failed"
    not_run = "not_run"


class ComicReading(StrEnum):
    supported = "supported"
    not_supported = "not_supported"
    ambiguous = "ambiguous"
    insufficient_context = "insufficient_context"


class EngineError(Strict):
    code: str
    message: str
    task: TaskName | None = None
    retryable: bool = False


class TaskResult(Strict):
    task: TaskName
    status: TaskStatus
    output_ref: str | None = None
    errors: list[EngineError] = Field(default_factory=list)


class Versions(Strict):
    engine: str
    taxonomy: str
    prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    retrieval_snapshot: str | None = None


class Evidence(Strict):
    evidence_id: str
    segment_id: str
    modality: Modality = Modality.text
    start: int = Field(ge=0, description="Half-open Unicode code-point offset into the original segment text")
    end: int = Field(ge=0)
    exact_text: str

    @model_validator(mode="after")
    def _ordered(self) -> Evidence:
        if self.end <= self.start:
            raise ValueError("evidence end must be greater than start")
        return self


class HumourAttempt(Strict):
    status: Literal["reported", "supported_inference", "not_established"]
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ReportedIntent(Strict):
    whose_intent: str
    reported_by: str
    evidence_ref: str | None = None
    basis: Literal["direct_declaration", "second_hand_report", "inference"]
    statement: str


class Uncertainty(Strict):
    """Confidence is explicit about its kind. Unknown is null, never zero."""

    score: float | None = Field(default=None, ge=0, le=1)
    score_kind: Literal["uncalibrated_model_score", "calibrated_probability", "unknown"] = "unknown"
    calibration_ref: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _kind_consistent(self) -> Uncertainty:
        if self.score_kind == "unknown" and self.score is not None:
            raise ValueError("score must be null when score_kind is unknown")
        if self.score_kind == "calibrated_probability" and not self.calibration_ref:
            raise ValueError("calibrated_probability requires calibration_ref")
        return self


class TargetSubject(Strict):
    subject: str | None = None
    target: Literal[
        "self", "other_person", "behaviour", "situation", "institution", "convention", "fictional_person", "none", "unknown"
    ] = "unknown"
    perspective: str | None = None


class Interpretation(Strict):
    id: str
    literal_reading: str
    supported_reading: str | None = None
    reported_intent: ReportedIntent | None = None
    structure_kind: str | None = None
    expectations: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    connecting_logic: str | None = None
    labels_by_axis: dict[str, list[str]] = Field(default_factory=dict)
    target_and_subject: TargetSubject = Field(default_factory=TargetSubject)
    evidence_refs: list[str] = Field(default_factory=list)
    contextual_claim_refs: list[str] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    uncertainty: Uncertainty = Field(default_factory=Uncertainty)
    is_main: bool = False


class ContextDependency(Strict):
    id: str
    claim: str
    source_kind: Literal[
        "linguistic", "topical", "cultural", "interpersonal", "earlier_turn", "visual", "acoustic", "provided_fact"
    ]
    source_ref: str | None = None
    required: bool = False
    verification_status: Literal["supplied", "verified_in_input", "assumed", "unverified"] = "unverified"


class Counterfactual(Strict):
    supplied_or_synthetic: Literal["supplied", "synthetic"]
    intervention: str
    expected_change: str | None = None
    observed_change: str | None = None
    original_analysis_id: str | None = None
    variant_analysis_id: str | None = None
    original_input_revision: str | None = None
    variant_input_revision: str | None = None
    human_validated: bool = False


class AudienceAssessment(Strict):
    profile_id: str
    profile_version: int
    basis: list[str] = Field(default_factory=list)
    scope: str
    score_kind: Literal["descriptive_rule_fit", "unknown"] = "descriptive_rule_fit"
    fit: Literal["match", "mismatch", "mixed", "unknown"]
    supporting_example_ids: list[str] = Field(default_factory=list)
    conflicting_example_ids: list[str] = Field(default_factory=list)
    uncertainty: Uncertainty = Field(default_factory=Uncertainty)
    limitations: list[str] = Field(default_factory=list)


class Attribution(Strict):
    model: str
    prediction: str
    method: str
    features: list[tuple[str, float]]
    settings: dict[str, float | int | str]
    fidelity: float | None
    stability: float | None = None
    limitations: list[str] = Field(default_factory=list)


class StylePrediction(Strict):
    """Source-specific social-function prediction. Not a comprehension result."""

    model: str
    label_namespace: str
    distribution: dict[str, float]
    predicted: str
    uncertainty: Uncertainty
    limitations: list[str] = Field(default_factory=list)


class Truncation(Strict):
    occurred: bool = False
    omitted_segments: list[str] = Field(default_factory=list)
    potentially_lost_payoff: bool = False


class Usage(Strict):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0
    elapsed_ms: int = 0
    measured_cost_usd: float | None = None
    cost_status: Literal["measured", "estimated", "unknown", "not_applicable"] = "not_applicable"


class AnalysisResult(Strict):
    # identity
    analysis_id: str
    request_id: str
    input_revision: str
    schema_version: Literal["1"] = SCHEMA_VERSION
    versions: Versions
    # execution
    analysis_mode: AnalysisMode
    modalities_actually_processed: list[Modality] = Field(default_factory=list)
    requested_tasks: list[TaskName]
    task_results: list[TaskResult]
    status: ResultStatus
    # semantics (present only when semantic analysis ran)
    comic_reading: ComicReading | None = None
    humour_attempt: HumourAttempt | None = None
    interpretations: list[Interpretation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    context_dependencies: list[ContextDependency] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    counterfactual_analysis: Counterfactual | None = None
    audience_assessment: AudienceAssessment | None = None
    style_prediction: StylePrediction | None = None
    attributions: list[Attribution] = Field(default_factory=list)
    truncation: Truncation = Field(default_factory=Truncation)
    usage: Usage = Field(default_factory=Usage)
    limitations: list[str] = Field(default_factory=list)
    errors: list[EngineError] = Field(default_factory=list)

    @field_validator("task_results")
    @classmethod
    def _unique_tasks(cls, v: list[TaskResult]) -> list[TaskResult]:
        names = [t.task for t in v]
        if len(names) != len(set(names)):
            raise ValueError("task_results must not repeat a task")
        return v

    @model_validator(mode="after")
    def _completion_invariants(self) -> AnalysisResult:
        by_task = {t.task: t for t in self.task_results}
        if set(by_task) != set(self.requested_tasks):
            raise ValueError("every requested task needs exactly one task_result")
        statuses = [t.status for t in self.task_results]
        if self.status == ResultStatus.complete and any(s != TaskStatus.complete for s in statuses):
            raise ValueError("status complete requires every requested task to be complete")
        comp = by_task.get(TaskName.comprehension)
        semantic_ran = comp is not None and comp.status == TaskStatus.complete
        if self.comic_reading is not None and not semantic_ran:
            raise ValueError("comic_reading may only be present when comprehension completed")
        if self.status in (ResultStatus.failed, ResultStatus.unsupported) and self.interpretations:
            raise ValueError("failed or unsupported results carry no interpretations")
        ev_ids = [e.evidence_id for e in self.evidence]
        if len(ev_ids) != len(set(ev_ids)):
            raise ValueError("evidence ids must be unique")
        known = set(ev_ids)
        for interp in self.interpretations:
            unknown = [r for r in interp.evidence_refs if r not in known]
            if unknown:
                raise ValueError(f"interpretation {interp.id} references unknown evidence {unknown}")
        if sum(1 for i in self.interpretations if i.is_main) > 1:
            raise ValueError("at most one main interpretation")
        if self.comic_reading == ComicReading.ambiguous and any(i.is_main for i in self.interpretations):
            raise ValueError("an ambiguous reading must not declare a main interpretation")
        return self
