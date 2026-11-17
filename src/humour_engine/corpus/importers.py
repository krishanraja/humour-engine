"""Source-specific importers. Each one consults the registry before reading anything.

Importers verify columns, label domains, nulls and row counts against what the
registry recorded; they never assume "all columns but the last" are text.
"""

from __future__ import annotations

import json
from pathlib import Path

from humour_engine.analysis.text import canonical_text_id, normalise_for_identity, sha
from humour_engine.contracts.corpus import CorpusRecord, Label
from humour_engine.operations.registry import Registry

MK5 = {0: "self-enhancing", 1: "self-deprecating", 2: "affiliative", 3: "aggressive", 4: "neutral"}
MK4 = {0: "self-enhancing", 1: "self-deprecating", 2: "affiliative_or_aggressive", 3: "neutral"}
AFAG = {0: "affiliative", 1: "aggressive"}
MAX_JSON_FIELD = 200_000


class ImportProblem(ValueError):
    pass


def _record(source_id, asset, row_ref, text, labels, **kw) -> CorpusRecord:
    return CorpusRecord(
        record_id=f"{source_id}:{asset}:{row_ref}",
        canonical_text_id=canonical_text_id(text),
        text_raw=text,
        text_normalised=normalise_for_identity(text),
        text_revision="sha256:" + sha(text),
        source_id=source_id,
        asset_path=asset,
        row_ref=row_ref,
        labels=labels,
        **kw,
    )


def _check(registry: Registry, source_id: str, asset: str, root: Path, operation: str = "ingestion") -> Path:
    registry.require(source_id, operation, asset)
    ok, msg = registry.verify_asset(source_id, asset, root)
    if not ok:
        raise ImportProblem(f"{source_id}/{asset}: {msg}")
    return root / asset


def _read_xlsx(path: Path):
    import pandas as pd

    return pd.read_excel(path)


def _expect_columns(df, cols: list[str], where: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ImportProblem(f"{where}: missing columns {missing}; found {list(df.columns)[:10]}")


def import_mk_xlsx(registry: Registry, root: Path, asset: str, namespace: str) -> list[CorpusRecord]:
    path = _check(registry, "S02", asset, root)
    df = _read_xlsx(path)
    _expect_columns(df, ["JOKES", "LABELS"], asset)
    mapping = MK5 if namespace == "mk5" else MK4
    expected = registry.asset("S02", asset).get("rows_observed")
    if expected is not None and len(df) != expected:
        raise ImportProblem(f"{asset}: {len(df)} rows, registry recorded {expected}")
    out = []
    for i, row in df.iterrows():
        text, lab = row["JOKES"], row["LABELS"]
        if not isinstance(text, str) or not text.strip():
            raise ImportProblem(f"{asset} row {i}: empty text")
        if int(lab) not in mapping:
            raise ImportProblem(f"{asset} row {i}: label {lab} outside {sorted(mapping)}")
        if registry.is_excluded("S02", f"{namespace}:{i}"):
            continue
        out.append(
            _record(
                "S02", asset, f"{namespace}:{i}", text,
                [Label(namespace=namespace, value=mapping[int(lab)], produced_by="imported_unknown", producer_id="S02")],
            )
        )
    return out


def import_mk_afag(registry: Registry, root: Path, asset: str) -> list[CorpusRecord]:
    import csv

    path = _check(registry, "S02", asset, root)
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["jokes", "labels"]:
            raise ImportProblem(f"{asset}: unexpected columns {reader.fieldnames}")
        for i, row in enumerate(reader):
            lab = int(row["labels"])
            if lab not in AFAG:
                raise ImportProblem(f"{asset} row {i}: label {lab}")
            ref = f"afag:{Path(asset).stem}:{i}"
            if registry.is_excluded("S02", ref):
                continue
            out.append(
                _record(
                    "S02", asset, ref, row["jokes"],
                    [Label(namespace="mk_af_ag", value=AFAG[lab], produced_by="imported_unknown", producer_id="S02",
                           note="upstream split ignored; engine assigns its own")],
                )
            )
    return out


def parse_json_string(value, field: str, warnings: list[str]):
    """Strictly decode a JSON-encoded string field. Never eval. Bounded size."""
    if not isinstance(value, str):
        return value
    if len(value) > MAX_JSON_FIELD:
        warnings.append(f"{field}: oversized ({len(value)} chars); kept raw")
        return {"_raw": value[:1000], "_truncated": True}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, RecursionError):
        warnings.append(f"{field}: not valid JSON; kept raw")
        return {"_raw": value}


XAI_JSON_FIELDS = (
    "class_probabilities", "top_features", "emotion_distribution", "linguistic_details",
    "detailed_analysis", "humor_mechanisms", "target_analysis", "linguistic_complexity",
)
XAI_MEASUREMENTS = (
    "primary_emotion", "dominant_sentiment", "sentiment_confidence", "sentiment_polarity", "sentiment_subjectivity",
    "sarcasm_probability", "is_sarcastic", "has_contrast", "exaggeration_count", "intensifier_count",
    "semantic_conflict_count", "rhyme_count", "has_alliteration", "self_reference_count", "pun_count",
    "syllable_complexity", "homonym_count",
)


def import_xai_json_dir(registry: Registry, root: Path, asset: str = "linguistic_affective_analysis_json/") -> list[CorpusRecord]:
    d = _check(registry, "S01", asset, root)
    out = []
    files = sorted(d.glob("detailed_analysis_*.json"), key=lambda p: int(p.stem.split("_")[-1]))
    for p in files:
        idx = p.stem.split("_")[-1]
        ref = f"xai:{idx}"
        if registry.is_excluded("S01", ref):
            continue
        if p.stat().st_size > 5_000_000:
            raise ImportProblem(f"{p.name}: file too large")
        obj = json.loads(p.read_text(encoding="utf-8"))
        warnings: list[str] = []
        text, label = obj.get("joke"), obj.get("label")
        if not isinstance(text, str):
            raise ImportProblem(f"{p.name}: no joke text")
        labels = []
        if isinstance(label, int) and label in MK5:
            labels.append(Label(namespace="mk5", value=MK5[label], produced_by="imported_unknown", producer_id="S01"))
        else:
            warnings.append(f"label {label!r} outside mk5")
        probs = parse_json_string(obj.get("class_probabilities"), "class_probabilities", warnings)
        preds = [
            Label(
                namespace="mk5",
                value=str(obj.get("predicted_class")),
                produced_by="model",
                producer_id="S01:GTE+XGBoost (upstream, not re-run)",
                note=json.dumps({"confidence_score": obj.get("confidence_score"), "class_probabilities": probs}),
            )
        ]
        meas = {k: obj.get(k) for k in XAI_MEASUREMENTS if k in obj}
        for k in XAI_JSON_FIELDS:
            if k in obj:
                meas[k] = parse_json_string(obj[k], k, warnings)
        meas["_provenance"] = "machine-derived descriptive measurement; not ground truth, not a classifier input"
        out.append(
            _record("S01", asset, ref, text, labels, predictions=preds, descriptive_measurements=meas, parse_warnings=warnings)
        )
    return out


def import_isarcasm(registry: Registry, root: Path, asset: str = "train/train.En.csv", operation: str = "ingestion") -> list[CorpusRecord]:
    import csv

    path = _check(registry, "S06", asset, root, operation)
    out = []
    cats = ["sarcasm", "irony", "satire", "understatement", "overstatement", "rhetorical_question"]
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        text_col = "tweet" if "tweet" in (reader.fieldnames or []) else "text"
        if text_col not in (reader.fieldnames or []) or "sarcastic" not in reader.fieldnames:
            raise ImportProblem(f"{asset}: unexpected columns {reader.fieldnames}")
        for i, row in enumerate(reader):
            text = row[text_col]
            if not text or not text.strip():
                continue
            ref = f"isarc:{Path(asset).stem}:{i}"
            if registry.is_excluded("S06", ref):
                continue
            labels = [Label(namespace="isarcasm", value="sarcastic" if row["sarcastic"] == "1" else "not_sarcastic",
                            produced_by="original_author")]
            for c in cats:
                if row.get(c) == "1":
                    labels.append(Label(namespace="isarcasm", value=c, produced_by="human_annotator"))
            rec = _record("S06", asset, ref, text, labels)
            out.append(rec)
            reph = (row.get("rephrase") or "").strip()
            if reph:
                out.append(
                    _record(
                        "S06", asset, ref + ":rephrase", reph,
                        [Label(namespace="isarcasm", value="not_sarcastic", produced_by="original_author",
                               note="author-written non-sarcastic rephrase of the parent")],
                        parent_record_id=rec.record_id,
                    )
                )
    return out
