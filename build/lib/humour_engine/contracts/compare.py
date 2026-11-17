"""Comparison of two input revisions or two context variants under one shared budget."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from humour_engine.contracts.analysis import (
    AnalysisResult,
    Budget,
    ContextBlock,
    EngineError,
    ProviderPolicy,
    Segment,
)
from humour_engine.contracts.base import Strict


class Variant(Strict):
    label: str = Field(min_length=1, max_length=64)
    segments: list[Segment] = Field(min_length=1)
    context: ContextBlock = Field(default_factory=ContextBlock)


class CompareRequest(Strict):
    schema_version: Literal["1"] = "1"
    request_id: str = Field(min_length=1, max_length=128)
    language: str = "en"
    focus_segment_ids: list[str] = Field(min_length=1)
    variant_a: Variant
    variant_b: Variant
    dimensions: list[
        Literal["comic_reading", "mechanisms", "rhetorical_modes", "social_function", "context_dependency", "target"]
    ] = Field(default_factory=lambda: ["comic_reading", "mechanisms", "context_dependency"])
    provider_policy: ProviderPolicy = Field(default_factory=ProviderPolicy)
    budget: Budget = Field(default_factory=lambda: Budget(max_model_calls=2))

    @model_validator(mode="after")
    def _distinct(self) -> CompareRequest:
        if self.variant_a.label == self.variant_b.label:
            raise ValueError("variant labels must differ")
        return self


class Difference(Strict):
    dimension: str
    a: list[str] | str | None
    b: list[str] | str | None
    grounded_in: list[str] = Field(default_factory=list, description="evidence or context ids from either analysis")


class CompareResult(Strict):
    comparison_id: str
    request_id: str
    status: Literal["complete", "partial", "failed"]
    analysis_a: AnalysisResult | None
    analysis_b: AnalysisResult | None
    differences: list[Difference] = Field(default_factory=list)
    invariances: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    shared_budget_calls_used: int = 0
    errors: list[EngineError] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
