"""Corpus record contract. Raw, normalised, predicted and adjudicated values stay separate."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from humour_engine.contracts.base import Strict

AnnotatorKind = Literal["original_author", "human_annotator", "adjudicator", "model", "heuristic", "imported_unknown"]


class Label(Strict):
    namespace: str = Field(description="e.g. mk5 (MaryKenneth five-class), mk4, mk_af_ag, isarcasm, engine")
    value: str
    produced_by: AnnotatorKind
    producer_id: str | None = None
    note: str | None = None


class MappedLabel(Strict):
    source: Label
    target_namespace: str
    target_value: str | None
    relation: Literal["equivalent", "broader", "narrower", "overlapping", "unmapped"]
    mapping_ref: str


class CorpusRecord(Strict):
    record_id: str = Field(description="stable id: <source_id>:<asset>:<row>")
    canonical_text_id: str = Field(description="hash of normalised text; shared by duplicates and label views")
    text_raw: str
    text_normalised: str
    text_revision: str = Field(description="sha256 of text_raw")
    source_id: str
    asset_path: str
    row_ref: str
    labels: list[Label] = Field(default_factory=list)
    mapped_labels: list[MappedLabel] = Field(default_factory=list)
    predictions: list[Label] = Field(default_factory=list, description="machine predictions; never ground truth")
    descriptive_measurements: dict[str, object] = Field(default_factory=dict)
    parse_warnings: list[str] = Field(default_factory=list)
    author_group: str | None = None
    source_group: str | None = None
    conversation_group: str | None = None
    family_id: str | None = Field(default=None, description="joke family; filled by grouping")
    parent_record_id: str | None = None
    split: Literal["train", "dev", "calibration", "test"] | None = None
