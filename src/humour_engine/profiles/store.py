"""File-backed profile store, isolated per owner scope. Persistence only under explicit retention."""

from __future__ import annotations

import re
from pathlib import Path

from humour_engine.contracts.profile import TasteProfile

SAFE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class ProfileStore:
    def __init__(self, root: Path, owner_scope: str | None = None):
        self.root = root
        self.owner_scope = owner_scope

    def _path(self, profile_id: str) -> Path:
        if not SAFE.match(profile_id):
            raise ValueError("invalid profile id")
        return self.root / f"{profile_id}.json"

    def get(self, profile_id: str) -> TasteProfile | None:
        p = self._path(profile_id)
        if not p.exists():
            return None
        prof = TasteProfile.model_validate_json(p.read_text())
        if self.owner_scope is not None and prof.owner_scope != self.owner_scope:
            return None  # never serve another scope's profile
        return prof

    def version_of(self, profile_id: str) -> int | None:
        prof = self.get(profile_id)
        return prof.version if prof else None

    def save_candidate(self, prof: TasteProfile) -> Path:
        if self.owner_scope is not None and prof.owner_scope != self.owner_scope:
            raise PermissionError("cannot write a profile for another scope")
        existing = self.get(prof.profile_id)
        if existing is not None and existing.version >= prof.version:
            raise ValueError("a new candidate must carry a higher version; profiles are versioned, not overwritten")
        self.root.mkdir(parents=True, exist_ok=True)
        p = self._path(prof.profile_id)
        p.write_text(prof.model_dump_json(indent=1))
        return p
