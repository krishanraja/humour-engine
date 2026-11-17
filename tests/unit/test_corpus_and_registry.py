"""Registry enforcement, JSON parsing, duplicates crossing splits, retrieval leakage (classes 8-11)."""

import json

import pytest
import yaml

from humour_engine.analysis.retrieval import retrieve_cards
from humour_engine.contracts.corpus import CorpusRecord, Label
from humour_engine.corpus import importers as I
from humour_engine.corpus import splits as S
from humour_engine.operations.registry import Registry, SourceDenied


def _registry(tmp_path, **over):
    data = yaml.safe_load(open(Registry().path))
    for s in data["sources"]:
        s.update(over.get(s["id"], {}))
    data["excluded_records"] = over.get("excluded", [])
    p = tmp_path / "registry.yaml"
    p.write_text(yaml.safe_dump(data))
    return Registry(p)


def test_unknown_source_denied():
    assert not Registry().decide("S99", "ingestion").allowed


def test_inactive_source_denied_for_every_consumer(tmp_path):
    reg = _registry(tmp_path, S02={"status": "dormant"})
    for op in ("ingestion", "training", "retrieval", "evaluation", "redistribution"):
        assert not reg.decide("S02", op).allowed
    with pytest.raises(SourceDenied):
        I.import_mk_xlsx(reg, tmp_path, "humour_styles_dataset/Humour_style.xlsx", "mk5")


def test_evaluation_only_asset_cannot_train_or_retrieve():
    reg = Registry()
    assert reg.decide("S06", "evaluation", "test/task_A_En_test.csv").allowed
    assert not reg.decide("S06", "training", "test/task_A_En_test.csv").allowed
    assert not reg.decide("S06", "retrieval", "test/task_A_En_test.csv").allowed


def test_hash_mismatch_blocks_import(tmp_path):
    reg = Registry()
    d = tmp_path / "humour_styles_dataset"
    d.mkdir()
    (d / "af_ag_train.csv").write_text("jokes,labels\nx,0\n")
    with pytest.raises(I.ImportProblem, match="hash mismatch"):
        I.import_mk_afag(reg, tmp_path, "humour_styles_dataset/af_ag_train.csv")


def test_strict_json_string_parsing_never_evals():
    w = []
    assert I.parse_json_string('{"a": 1}', "f", w) == {"a": 1}
    out = I.parse_json_string("__import__('os').system('echo hacked')", "f", w)
    assert out == {"_raw": "__import__('os').system('echo hacked')"} and w
    big = I.parse_json_string("[" * 10 + "1" + "]" * 10, "f", [])
    assert big == [[[[[[[[[[1]]]]]]]]]]
    w2 = []
    assert I.parse_json_string("x" * (I.MAX_JSON_FIELD + 1), "f", w2)["_truncated"] and w2


def test_deeply_nested_payload_is_safe():
    w = []
    out = I.parse_json_string("[" * 100000 + "]" * 100000, "f", w)
    assert isinstance(out, dict) and w


def test_xai_import_keeps_predictions_separate(sources_root):
    recs = I.import_xai_json_dir(Registry(), sources_root / "XAI_humour_styles")
    assert len(recs) == 293
    r = recs[0]
    assert all(lab.produced_by != "model" for lab in r.labels)
    assert r.predictions and r.predictions[0].produced_by == "model"
    assert "not ground truth" in r.descriptive_measurements["_provenance"]


def _rec(rid, text, parent=None):
    from humour_engine.analysis.text import canonical_text_id, normalise_for_identity

    return CorpusRecord(record_id=rid, canonical_text_id=canonical_text_id(text), text_raw=text,
                        text_normalised=normalise_for_identity(text), text_revision="x", source_id="ENG",
                        asset_path="t", row_ref=rid, labels=[Label(namespace="t", value="a", produced_by="heuristic")],
                        parent_record_id=parent)


def test_duplicates_and_derivatives_never_cross_splits():
    recs = []
    for i in range(300):
        base = f"joke number {i} about a very particular thing {i * 7919}"
        recs.append(_rec(f"a{i}", base))
        recs.append(_rec(f"b{i}", "  " + base.upper() + "  "))  # normalised duplicate
        recs.append(_rec(f"c{i}", f"completely rewritten variant {i * 31}", parent=f"a{i}"))  # derivative
    S.assign_groups(recs)
    m = S.make_manifest(recs, "t", "salt")
    assert S.verify_manifest(m) == []
    assert S.overlap_report(recs) == {"texts_crossing": [], "families_crossing": []}
    parts = {r.record_id: r.split for r in recs}
    assert all(parts[f"a{i}"] == parts[f"b{i}"] == parts[f"c{i}"] for i in range(300))
    assert len({r.split for r in recs}) == 4


def test_tampered_manifest_detected():
    recs = [_rec(f"a{i}", f"text {i} {i * 13}") for i in range(40)]
    S.assign_groups(recs)
    m = S.make_manifest(recs, "t", "salt")
    m["partitions"]["test"]["canonical_text_ids"].append(m["partitions"]["train"]["canonical_text_ids"][0])
    assert S.verify_manifest(m)


def test_retrieval_never_returns_the_analysed_item_or_heldout_items():
    q = "The committee has appointed a committee to reduce the number of committees."
    cards, _ = retrieve_cards([q])
    assert all(q not in json.dumps(c.data) for c in cards)
    blocked = "The bank promised interest. I am still bored."
    cards2, _ = retrieve_cards(["bank interest bored"], blocklist={blocked})
    assert all(blocked not in json.dumps(c.data) for c in cards2)


def test_retrieval_ablation_off():
    assert retrieve_cards(["committee"], mode="off") == ([], None)
