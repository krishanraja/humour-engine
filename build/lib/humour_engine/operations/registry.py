"""Source registry: the single control every corpus consumer consults.

Operations: reference, ingestion, training, retrieval, evaluation, redistribution.
No licence gating (all sources owned, Ruling Krish 2026-11-17). The registry still
enforces activation status, record exclusions and evaluation-only assets so that a
removed or held-out item cannot reach training, retrieval or exports by a side path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = REPO_ROOT / "sources" / "registry.yaml"

OPERATIONS = ("reference", "ingestion", "training", "retrieval", "evaluation", "redistribution")


class SourceDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


class Registry:
    def __init__(self, path: Path = DEFAULT_REGISTRY):
        self.path = path
        self.data = yaml.safe_load(path.read_text())
        self.sources = {s["id"]: s for s in self.data["sources"]}
        self._excluded = {(e["source_id"], e["row_ref"]): e for e in self.data.get("excluded_records") or []}

    def asset(self, source_id: str, asset_path: str) -> dict | None:
        for a in self.sources.get(source_id, {}).get("assets", []):
            if a["path"] == asset_path:
                return a
        return None

    def decide(self, source_id: str, operation: str, asset_path: str | None = None) -> Decision:
        if operation not in OPERATIONS:
            return Decision(False, f"unknown operation {operation}")
        src = self.sources.get(source_id)
        if src is None:
            return Decision(False, f"unknown source {source_id}")
        status = src.get("status")
        if operation == "reference":
            return Decision(True, "reference is always allowed for registered sources")
        if status != "active":
            return Decision(False, f"source {source_id} is {status}, not active")
        if asset_path is not None:
            a = self.asset(source_id, asset_path)
            if a is None:
                return Decision(False, f"asset {asset_path} is not registered for {source_id}")
            if a.get("evaluation_only") and operation in ("training", "retrieval"):
                return Decision(False, f"{asset_path} is evaluation-only; {operation} denied")
        return Decision(True, "active owned source")

    def require(self, source_id: str, operation: str, asset_path: str | None = None) -> None:
        d = self.decide(source_id, operation, asset_path)
        if not d.allowed:
            raise SourceDenied(d.reason)

    def is_excluded(self, source_id: str, row_ref: str) -> bool:
        return (source_id, row_ref) in self._excluded

    def verify_asset(self, source_id: str, asset_path: str, root: Path) -> tuple[bool, str]:
        a = self.asset(source_id, asset_path)
        if a is None:
            return False, "unregistered asset"
        p = root / asset_path
        if not p.exists():
            return False, f"missing file {p}"
        if p.is_dir():
            return True, "directory (no hash recorded)"
        want = a.get("sha256")
        if not want:
            return True, "no hash recorded"
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        return got == want, ("hash ok" if got == want else f"hash mismatch {got[:12]} != {want[:12]}")

    def audit(self, roots: dict[str, Path] | None = None) -> list[dict]:
        roots = roots or {}
        rows = []
        for sid, s in self.sources.items():
            for a in s.get("assets", []) or [{"path": None}]:
                row = {
                    "source_id": sid,
                    "name": s["name"],
                    "commit": s.get("commit"),
                    "status": s.get("status"),
                    "asset": a.get("path"),
                    "evaluation_only": bool(a.get("evaluation_only")),
                }
                for op in OPERATIONS:
                    row[op] = self.decide(sid, op, a.get("path")).allowed
                if a.get("path") and sid in roots:
                    ok, msg = self.verify_asset(sid, a["path"], roots[sid])
                    row["verified"] = msg if ok else f"FAIL: {msg}"
                rows.append(row)
        return rows
