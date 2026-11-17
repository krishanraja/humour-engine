"""Grouping, deduplication and sealed split manifests.

Split once, then derive every task view from the same assignment. Groups:
exact/normalised text identity, parent/derivative links, and near-duplicate
candidates (co-located for safety, listed for human review, never merged).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from humour_engine.contracts.corpus import CorpusRecord

PARTITIONS = ("train", "dev", "calibration", "test")
DEFAULT_RATIOS = {"train": 0.60, "dev": 0.15, "calibration": 0.10, "test": 0.15}


class _UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def near_duplicate_pairs(texts: dict[str, str], threshold: float = 0.85) -> list[tuple[str, str, float]]:
    """Candidate near-duplicates by char 3-5gram TF-IDF cosine. Discovery only."""
    if len(texts) < 2:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer

    ids = sorted(texts)
    X = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1).fit_transform([texts[i] for i in ids])
    sims = (X @ X.T).tocoo()
    out = []
    for i, j, v in zip(sims.row, sims.col, sims.data, strict=True):
        if i < j and v >= threshold:
            out.append((ids[i], ids[j], round(float(v), 4)))
    return out


@dataclass
class GroupReport:
    n_records: int
    n_canonical_texts: int
    n_groups: int
    exact_duplicate_clusters: int
    near_duplicate_candidates: list[tuple[str, str, float]]
    label_conflicts: dict[str, dict[str, list[str]]]


def assign_groups(records: list[CorpusRecord], near_dup_threshold: float = 0.85) -> GroupReport:
    uf = _UF()
    by_id = {r.record_id: r for r in records}
    for r in records:
        uf.union("t:" + r.canonical_text_id, "t:" + r.canonical_text_id)
        if r.parent_record_id and r.parent_record_id in by_id:
            uf.union("t:" + r.canonical_text_id, "t:" + by_id[r.parent_record_id].canonical_text_id)
    canon = {}
    for r in records:
        canon.setdefault(r.canonical_text_id, r.text_normalised)
    near = near_duplicate_pairs(canon, near_dup_threshold)
    for a, b, _ in near:
        uf.union("t:" + a, "t:" + b)
    for r in records:
        r.family_id = "fam_" + uf.find("t:" + r.canonical_text_id)[2:]
    # label conflicts per canonical text, per namespace (human/imported labels only)
    labels: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for r in records:
        for lab in r.labels:
            labels[r.canonical_text_id][lab.namespace].add(lab.value)
    conflicts = {
        cid: {ns: sorted(v) for ns, v in nss.items() if len(v) > 1} for cid, nss in labels.items()
    }
    conflicts = {k: v for k, v in conflicts.items() if v}
    sizes = defaultdict(set)
    for r in records:
        sizes[r.canonical_text_id].add(r.source_id + r.asset_path)
    return GroupReport(
        n_records=len(records),
        n_canonical_texts=len(canon),
        n_groups=len({r.family_id for r in records}),
        exact_duplicate_clusters=sum(1 for c in canon if sum(1 for r in records if r.canonical_text_id == c) > 1),
        near_duplicate_candidates=near,
        label_conflicts=conflicts,
    )


def _bucket(group_id: str, salt: str) -> float:
    h = hashlib.sha256(f"{salt}:{group_id}".encode()).hexdigest()
    return int(h[:12], 16) / 16**12


def make_manifest(records: list[CorpusRecord], name: str, salt: str, ratios: dict[str, float] = DEFAULT_RATIOS) -> dict:
    if any(r.family_id is None for r in records):
        raise ValueError("assign_groups must run before splitting")
    cuts, acc = [], 0.0
    for p in PARTITIONS:
        acc += ratios[p]
        cuts.append((acc, p))
    group_part = {}
    for g in sorted({r.family_id for r in records}):
        b = _bucket(g, salt)
        group_part[g] = next(p for c, p in cuts if b < c + 1e-12)
    for r in records:
        r.split = group_part[r.family_id]
    parts: dict[str, dict] = {p: {"record_ids": [], "canonical_text_ids": set(), "groups": set()} for p in PARTITIONS}
    for r in sorted(records, key=lambda r: r.record_id):
        parts[r.split]["record_ids"].append(r.record_id)
        parts[r.split]["canonical_text_ids"].add(r.canonical_text_id)
        parts[r.split]["groups"].add(r.family_id)
    body = {
        "name": name,
        "salt": salt,
        "ratios": ratios,
        "grouping_policy": "exact+normalised text identity, parent/derivative links, near-duplicate candidates (char tf-idf cosine>=0.85) co-located",
        "disjointness_claimed": ["joke_family"],
        "disjointness_not_claimed": ["author", "source", "show"],
        "partitions": {
            p: {
                "n_records": len(v["record_ids"]),
                "n_texts": len(v["canonical_text_ids"]),
                "n_groups": len(v["groups"]),
                "record_ids": v["record_ids"],
                "canonical_text_ids": sorted(v["canonical_text_ids"]),
            }
            for p, v in parts.items()
        },
    }
    body["seal"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def verify_manifest(manifest: dict) -> list[str]:
    problems = []
    body = {k: v for k, v in manifest.items() if k != "seal"}
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != manifest.get("seal"):
        problems.append("seal mismatch: manifest was modified after sealing")
    seen: dict[str, str] = {}
    for p, v in manifest["partitions"].items():
        for cid in v["canonical_text_ids"]:
            if cid in seen and seen[cid] != p:
                problems.append(f"text {cid} crosses {seen[cid]} and {p}")
            seen[cid] = p
    return problems


def overlap_report(records: list[CorpusRecord]) -> dict:
    """Machine-checked: no canonical text and no family crosses partitions."""
    text_parts, fam_parts = defaultdict(set), defaultdict(set)
    for r in records:
        text_parts[r.canonical_text_id].add(r.split)
        fam_parts[r.family_id].add(r.split)
    return {
        "texts_crossing": sorted(k for k, v in text_parts.items() if len(v) > 1),
        "families_crossing": sorted(k for k, v in fam_parts.items() if len(v) > 1),
    }


def save_manifest(manifest: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True))


def apply_manifest(records: list[CorpusRecord], manifest: dict) -> list[CorpusRecord]:
    """Assign splits from a sealed manifest by canonical text id (label views follow their text)."""
    problems = verify_manifest(manifest)
    if problems:
        raise ValueError("; ".join(problems))
    cid_part = {cid: p for p, v in manifest["partitions"].items() for cid in v["canonical_text_ids"]}
    for r in records:
        if r.canonical_text_id not in cid_part:
            raise ValueError(f"record {r.record_id} text is not in the sealed manifest")
        r.split = cid_part[r.canonical_text_id]
    return records
