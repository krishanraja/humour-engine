"""Explicit, versioned taste profiles. A profile is never inferred from unrelated private data."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from humour_engine.contracts.base import Strict


class FeedbackItem(Strict):
    item_id: str
    text: str
    judgement: Literal["approved", "rejected", "near_miss"]
    reason: str | None = None
    labels_by_axis: dict[str, list[str]] = Field(
        default_factory=dict, description="mechanisms/modes the owner or a reviewed analysis attached"
    )
    context: str | None = Field(default=None, description="where this applies, e.g. 'work slack', 'stage'")
    recorded_at: str | None = None
    understood_but_would_not_publish: bool = False


class PairwisePreference(Strict):
    pair_id: str
    preferred_item_id: str
    other_item_id: str
    reason: str | None = None
    recorded_at: str | None = None


class AxisPreference(Strict):
    axis: str
    value: str
    direction: Literal["prefer", "avoid"]
    support_example_ids: list[str]
    against_example_ids: list[str] = Field(default_factory=list)
    support: int
    confidence: Literal["low", "medium", "high"]
    context: str | None = None
    provenance: str = "derived_from_explicit_feedback"


class TasteProfile(Strict):
    profile_id: str
    owner_scope: str
    version: int = Field(ge=1)
    approval_state: Literal["candidate", "approved", "retired"] = "candidate"
    preferences: list[AxisPreference] = Field(default_factory=list)
    positive_example_ids: list[str] = Field(default_factory=list)
    disliked_example_ids: list[str] = Field(default_factory=list)
    near_miss_example_ids: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    built_from_feedback_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
