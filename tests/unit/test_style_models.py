"""Label-space mapping, hierarchical composition, empty routes, normalisation (classes 6, 7)."""

import numpy as np
import pytest

from humour_engine.corpus.importers import AFAG, MK4, MK5
from humour_engine.models.style import (
    BINARY_TO_FINAL,
    FINAL,
    FINAL_TO_GATE,
    StyleModel,
    compose_hierarchical,
    temper,
)
from humour_engine.taxonomy import load_crosswalk


def test_mappings_match_crosswalk_file():
    cw = load_crosswalk("mk5_to_engine")
    assert {int(k): v for k, v in cw["label_ids"].items()} == MK5
    assert {int(k): v for k, v in cw["gate"]["final_to_gate"].items()} == FINAL_TO_GATE
    assert {int(k): v for k, v in cw["gate"]["binary_specialist"].items()} == BINARY_TO_FINAL
    assert FINAL == [MK5[i] for i in range(5)]


def test_neutral_maps_to_gate_3_and_back_to_final_4():
    assert FINAL_TO_GATE[4] == 3
    assert MK4[3] == "neutral" and MK5[4] == "neutral"
    gate = np.array([[0, 0, 0, 1.0]])
    out = compose_hierarchical(gate, np.array([[0.5, 0.5]]))
    assert out[0].argmax() == 4


def test_binary_specialist_alignment():
    assert AFAG == {0: "affiliative", 1: "aggressive"}
    out = compose_hierarchical(np.array([[0, 0, 1.0, 0]]), np.array([[0.2, 0.8]]))
    assert FINAL[int(out[0].argmax())] == "aggressive"


def test_soft_composition_normalises():
    rng = np.random.default_rng(0)
    g = rng.dirichlet(np.ones(4), size=50)
    b = rng.dirichlet(np.ones(2), size=50)
    out = compose_hierarchical(g, b)
    assert np.allclose(out.sum(axis=1), 1.0)
    assert np.allclose(out[:, 2] + out[:, 3], g[:, 2])


def test_shape_mismatch_rejected():
    with pytest.raises(ValueError):
        compose_hierarchical(np.ones((2, 5)), np.ones((2, 2)))


def test_no_threshold_relabelling_low_affiliative_stays_affiliative():
    # affiliative argmax with p<=0.65 must not be relabelled aggressive without evidence
    out = compose_hierarchical(np.array([[0.2, 0.2, 0.6, 0.0]]), np.array([[0.9, 0.1]]))
    assert FINAL[int(out[0].argmax())] == "affiliative" and out[0, 2] < 0.65


TEXTS = [
    "I am great at everything", "I'm the best, obviously", "I always mess things up", "I'm hopeless at this",
    "we all love a good laugh together", "friends who laugh together stay together",
    "you're so dumb it hurts", "nobody likes you anyway", "the bus departs at nine", "the report is due monday",
] * 3
LABELS = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4] * 3


@pytest.mark.parametrize("variant", ["single", "hierarchical"])
def test_full_distribution_and_empty_batches(variant):
    m = StyleModel(variant=variant, C=1.0).fit(TEXTS, LABELS)
    p = m.predict_proba(["you are dumb", "the bus is late"])
    assert p.shape == (2, 5) and np.allclose(p.sum(1), 1)
    assert m.predict_proba([]).shape == (0, 5)
    assert m.predict_proba(["single"]).shape == (1, 5)


def test_specialist_requires_both_classes():
    with pytest.raises(ValueError, match="specialist"):
        StyleModel(variant="hierarchical", C=1.0).fit(TEXTS[:4] + TEXTS[8:10], [0, 0, 1, 1, 4, 4])


def test_temperature_preserves_argmax_and_normalises():
    p = np.array([[0.1, 0.2, 0.7, 0, 0]])
    q = temper(p, 2.0)
    assert q.argmax() == 2 and np.isclose(q.sum(), 1)


def test_artifact_digest_checked(tmp_path):
    m = StyleModel(variant="single", C=1.0).fit(TEXTS, LABELS)
    path = tmp_path / "m.pkl"
    m.save(path)
    assert StyleModel.load(path).predict_proba(["x"]).shape == (1, 5)
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="digest"):
        StyleModel.load(path)
