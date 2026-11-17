"""Pre-registered style-classifier experiment on the MaryKenneth five-class labels.

Protocol (frozen before the test partition is opened):
- Data: S02 Humour_style.xlsx (1463 texts) with S02 four-class/binary views and S01 XAI texts
  folded in by canonical text identity. One shared split by joke family.
- Systems: majority baseline; single five-class TF-IDF+LR; hierarchical gate+specialist (soft).
- Selection: C chosen on dev by macro-F1. Calibration: temperature on the calibration partition.
- Primary metric: test macro-F1; comparison hierarchical minus single, paired bootstrap 95% CI
  over independent texts. Secondary: per-class P/R/F1, Brier, ECE.
- The test partition is used once per frozen configuration; the test ledger refuses reuse.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np

from humour_engine.corpus import importers as I
from humour_engine.corpus import splits as S
from humour_engine.evaluation import metrics as M
from humour_engine.models.style import FINAL, StyleModel
from humour_engine.operations.registry import Registry
from humour_engine.operations.runs import RunStore, dumps

C_GRID = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
LABEL_ID = {v: k for k, v in I.MK5.items()}


def load_mk_records(registry: Registry, s01_root: Path, s02_root: Path):
    recs = I.import_mk_xlsx(registry, s02_root, "humour_styles_dataset/Humour_style.xlsx", "mk5")
    recs += I.import_mk_xlsx(registry, s02_root, "humour_styles_dataset/Humour_style_4classes.xlsx", "mk4")
    recs += I.import_mk_afag(registry, s02_root, "humour_styles_dataset/af_ag_train.csv")
    recs += I.import_mk_afag(registry, s02_root, "humour_styles_dataset/af_ag_test.csv")
    if s01_root is not None:
        recs += I.import_xai_json_dir(registry, s01_root)
    return recs


def task_view(records, partition: str) -> tuple[list[str], np.ndarray, list[str]]:
    """Derive the five-class task from the shared split: one row per canonical text."""
    seen, texts, ys, ids = set(), [], [], []
    for r in sorted(records, key=lambda r: r.record_id):
        if r.split != partition or r.canonical_text_id in seen:
            continue
        lab = next((lab.value for lab in r.labels if lab.namespace == "mk5"), None)
        if lab is None:
            continue
        seen.add(r.canonical_text_id)
        texts.append(r.text_raw)
        ys.append(LABEL_ID[lab])
        ids.append(r.canonical_text_id)
    return texts, np.asarray(ys), ids


def _scores(p: np.ndarray, y: np.ndarray) -> dict:
    yhat = p.argmax(axis=1)
    return {
        "macro_f1": round(M.macro_f1(y, yhat, 5), 4),
        "accuracy": round(M.micro_f1(y, yhat), 4),
        "brier": round(M.brier(p, y), 4),
        "per_class": M.per_class(y, yhat, FINAL),
        "confusion": M.confusion(y, yhat, 5).tolist(),
    }


def run(
    s01_root: Path | None,
    s02_root: Path,
    out_dir: Path,
    run_id: str = "style-mk5-v1",
    registry: Registry | None = None,
    open_test: bool = True,
) -> dict:
    registry = registry or Registry()
    seal_src = json.dumps(
        {"S01": registry.sources["S01"]["commit"], "S02": registry.sources["S02"]["commit"], "grid": C_GRID}
    )
    store = RunStore(out_dir / "runs", run_id, hashlib.sha256(seal_src.encode()).hexdigest())

    # stage 1-4: eligibility, parse, group, split (one sealed manifest)
    def build_split():
        recs = load_mk_records(registry, s01_root, s02_root)
        rep = S.assign_groups(recs)
        manifest = S.make_manifest(recs, "mk5-family-split", salt="humour-engine-2026-11-17")
        overlap = S.overlap_report(recs)
        if overlap["texts_crossing"] or overlap["families_crossing"]:
            raise RuntimeError(f"split overlap: {overlap}")
        return dumps(
            {
                "manifest": manifest,
                "group_report": {
                    "n_records": rep.n_records,
                    "n_canonical_texts": rep.n_canonical_texts,
                    "n_groups": rep.n_groups,
                    "texts_with_multiple_records": rep.exact_duplicate_clusters,
                    "near_duplicate_candidates_pending_review": rep.near_duplicate_candidates,
                    "label_conflicts": rep.label_conflicts,
                },
                "overlap": overlap,
            }
        )

    split_path = store.run_stage("split", "v1", store.path("split.json"), build_split)
    split = json.loads(split_path.read_text())
    manifest = split["manifest"]
    recs = S.apply_manifest(load_mk_records(registry, s01_root, s02_root), manifest)
    tr_x, tr_y, _ = task_view(recs, "train")
    dv_x, dv_y, _ = task_view(recs, "dev")
    ca_x, ca_y, _ = task_view(recs, "calibration")
    te_x, te_y, te_ids = task_view(recs, "test")

    # stage 5-6: train, select on dev, calibrate
    def train_select():
        out = {"dev": {}, "selected": {}}
        models = {}
        for variant in ("single", "hierarchical"):
            best = None
            for C in C_GRID:
                m = StyleModel(variant=variant, C=C).fit(tr_x, tr_y)
                f = M.macro_f1(dv_y, m.predict_proba(dv_x).argmax(1), 5)
                out["dev"][f"{variant}@C={C}"] = round(f, 4)
                if best is None or f > best[0]:
                    best = (f, m)
            m = best[1]
            m.train_manifest_seal = manifest["seal"]
            pre = M.brier(m.predict_proba(ca_x), ca_y)
            m.calibrate(ca_x, ca_y.tolist(), ref=f"temperature@{run_id}:calibration:{manifest['seal'][:12]}")
            out["selected"][variant] = {
                "C": m.C,
                "dev_macro_f1": round(best[0], 4),
                "temperature": round(m.temperature, 4),
                "calibration_brier_before": round(pre, 4),
            }
            models[variant] = m
        return pickle.dumps({"summary": out, "models": models})

    tpath = store.run_stage("train_select", "v1", store.path("models.pkl"), train_select)
    blob = pickle.loads(tpath.read_bytes())  # noqa: S301 - produced by this run, hash-checked by RunStore
    models, selection = blob["models"], blob["summary"]
    frozen = {
        "manifest_seal": manifest["seal"],
        "selected": selection["selected"],
        "features": "tfidf word1-2 + char_wb2-5",
        "primary_metric": "test macro-F1; hierarchical minus single, paired bootstrap 95% CI",
    }
    frozen_hash = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()

    report = {
        "run_id": run_id,
        "frozen_config": frozen,
        "frozen_config_hash": frozen_hash,
        "data": split["group_report"],
        "partition_sizes": {p: {"records": v["n_records"], "texts": v["n_texts"]} for p, v in manifest["partitions"].items()},
        "dev_selection": selection,
        "test": None,
    }
    if not open_test:
        return report

    # stage 7: sealed test, once per frozen config
    ledger_path = out_dir / "test_ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    used = ledger.get(manifest["seal"])
    if used and used != frozen_hash:
        raise RuntimeError(
            "this sealed test partition was already used by a different frozen configuration; "
            "retire it and create a new independent test before another confirmatory claim"
        )

    def test_eval():
        train_counts = np.bincount(tr_y, minlength=5)
        maj = np.tile(np.eye(5)[int(train_counts.argmax())], (len(te_y), 1))
        res = {"n_test_texts": int(len(te_y)), "majority_baseline": _scores(maj, te_y)}
        preds = {}
        for v, m in models.items():
            p = m.predict_proba(te_x)
            res[v] = _scores(p, te_y)
            res[v]["brier_uncalibrated"] = round(M.brier(m.raw_proba(te_x), te_y), 4)
            res[v]["reliability"] = M.reliability(p, te_y)
            res[v]["coverage_error"] = M.coverage_error_curve(p.max(1), p.argmax(1) == te_y)
            preds[v] = p.argmax(1)
        res["hierarchical_minus_single"] = M.paired_bootstrap(te_y, preds["single"], preds["hierarchical"], 5)
        res["single_minus_majority"] = M.paired_bootstrap(te_y, np.full(len(te_y), int(train_counts.argmax())), preds["single"], 5)
        res["denominator"] = {"eligible": int(len(te_y)), "answered": int(len(te_y)), "abstained": 0, "failed": 0, "excluded": 0}
        return dumps(res)

    test_path = store.run_stage("test_eval", "v1:" + frozen_hash[:12], store.path("test.json"), test_eval)
    ledger[manifest["seal"]] = frozen_hash
    ledger_path.write_text(json.dumps(ledger, indent=1))
    report["test"] = json.loads(test_path.read_text())

    # save the deployable model (single or hierarchical, whichever wins on dev; test never decides)
    best_variant = max(selection["selected"], key=lambda v: selection["selected"][v]["dev_macro_f1"])
    m = models[best_variant]
    m.meta = {"run_id": run_id, "frozen_config_hash": frozen_hash, "chosen_on": "dev macro-F1"}
    report["deployed_variant"] = best_variant
    report["deployed_artifact_sha256"] = m.save(out_dir / "style_model.pkl")
    return report
