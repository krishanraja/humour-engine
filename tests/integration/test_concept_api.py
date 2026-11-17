"""The consumer-facing API and the committed schemas stay in step with the code."""

import json
from pathlib import Path

import pytest

from humour_engine import concept

ROOT = Path(__file__).resolve().parents[2]


def test_committed_schemas_are_current(tmp_path):
    concept.export_schemas(tmp_path)
    for p in tmp_path.iterdir():
        committed = ROOT / "schemas" / p.name
        assert committed.exists(), f"missing {committed}; run `humour schemas`"
        assert json.loads(committed.read_text()) == json.loads(p.read_text()), f"{p.name} is stale; run `humour schemas`"


def test_define_and_ontology():
    assert "later turn" in concept.define("mechanism", "callback")
    with pytest.raises(KeyError):
        concept.define("mechanism", "hilarity")
    o = concept.ontology()
    assert o["axes"]["mechanism"]["multi"] is True
    assert "comic_reading" in o["axes"]


def test_cards_expose_evidence_requirements():
    cards = {c["id"]: c for c in concept.pattern_cards()}
    assert cards["lexical_pun_two_senses"]["insufficient_evidence"]
