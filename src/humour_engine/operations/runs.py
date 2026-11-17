"""Staged research runs with verified checkpoints.

Each stage owns its output file. A stage counts as complete only when its output
exists and its hash matches the recorded completion; a missing or altered output
reruns the stage. A heartbeat is never completion. Writes are atomic (tmp+rename).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path


class StageFailed(RuntimeError):
    pass


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RunStore:
    def __init__(self, root: Path, run_id: str, input_seal: str):
        self.root = root / run_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.db = sqlite3.connect(self.root / "run.sqlite")
        self.db.execute(
            "create table if not exists stages (name text primary key, version text, output text, "
            "output_hash text, completed_at real, attempts integer)"
        )
        self.db.execute("create table if not exists meta (k text primary key, v text)")
        row = self.db.execute("select v from meta where k='input_seal'").fetchone()
        if row is None:
            self.db.execute("insert into meta values ('input_seal', ?)", (input_seal,))
            self.db.commit()
        elif row[0] != input_seal:
            raise StageFailed("input seal changed since this run started; use a new run id")

    def path(self, name: str) -> Path:
        return self.root / name

    def is_complete(self, name: str, version: str) -> bool:
        row = self.db.execute("select version, output, output_hash from stages where name=?", (name,)).fetchone()
        if not row or row[0] != version or row[2] is None:
            return False
        p = Path(row[1])
        return p.exists() and file_hash(p) == row[2]

    def run_stage(
        self, name: str, version: str, output: Path, fn: Callable[[], bytes], max_attempts: int = 2
    ) -> Path:
        if self.is_complete(name, version):
            return output
        row = self.db.execute("select attempts from stages where name=?", (name,)).fetchone()
        attempts = row[0] if row else 0
        last = None
        while attempts < max_attempts:
            attempts += 1
            self.db.execute(
                "insert into stages(name,version,output,output_hash,completed_at,attempts) values(?,?,?,?,?,?) "
                "on conflict(name) do update set version=excluded.version, output_hash=null, attempts=excluded.attempts",
                (name, version, str(output), None, None, attempts),
            )
            self.db.commit()
            try:
                data = fn()
                if not data:
                    raise StageFailed(f"stage {name} produced empty output")
                atomic_write(output, data)
                self.db.execute(
                    "update stages set output_hash=?, completed_at=? where name=?", (file_hash(output), time.time(), name)
                )
                self.db.commit()
                return output
            except StageFailed as e:
                last = e
            except Exception as e:  # noqa: BLE001 - recorded and surfaced
                last = StageFailed(f"stage {name}: {type(e).__name__}: {e}")
        raise StageFailed(f"stage {name} exhausted {max_attempts} attempts: {last}")

    def status(self) -> list[dict]:
        rows = self.db.execute("select name, version, output_hash, completed_at, attempts from stages").fetchall()
        return [
            {"stage": r[0], "version": r[1], "complete": r[2] is not None, "attempts": r[4]} for r in rows
        ]


def dumps(obj) -> bytes:
    return json.dumps(obj, indent=1, sort_keys=True, default=str).encode()
