"""Taxonomy, pattern cards and crosswalk loading with release validation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge"

CARD_AXIS_TO_TAXONOMY = {
    "rhetorical_modes": "rhetorical_mode",
    "mechanisms": "mechanism",
    "register": "register",
    "textual_register": "register",
    "social_function": "social_function",
    "structure": "structure",
}


@dataclass(frozen=True)
class Taxonomy:
    version: str
    axes: dict[str, dict]
    modality_restricted: dict[str, list[str]]
    digest: str

    def values(self, axis: str) -> set[str]:
        vals = self.axes[axis]["values"]
        return set(vals) if isinstance(vals, list) else set(vals.keys())

    def is_multi(self, axis: str) -> bool:
        return bool(self.axes[axis].get("multi"))

    def label_axes(self) -> list[str]:
        return [a for a in self.axes if a not in ("comic_reading", "audience", "target", "context_dependency")]


@dataclass
class Card:
    id: str
    version: int
    data: dict
    tokens: frozenset[str] = field(default_factory=frozenset)


def _digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


@lru_cache(maxsize=4)
def load_taxonomy(knowledge_dir: Path = KNOWLEDGE_DIR) -> Taxonomy:
    path = knowledge_dir / "taxonomy" / "axes.yaml"
    data = yaml.safe_load(path.read_text())
    return Taxonomy(
        version=str(data["version"]),
        axes=data["axes"],
        modality_restricted=data.get("modality_restricted", {}),
        digest=_digest([path]),
    )


_WORD = re.compile(r"[a-z]+")
_STOP = frozenset("the a an of to and or is are was be i you it in on for with that this my as at by".split())


def tokens(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2)


@lru_cache(maxsize=4)
def load_cards(knowledge_dir: Path = KNOWLEDGE_DIR) -> tuple[Card, ...]:
    path = knowledge_dir / "patterns" / "cards.yaml"
    raw = yaml.safe_load(path.read_text())["cards"]
    out = []
    for c in raw:
        text = " ".join([c.get("definition", "")] + [str(x) for x in c.get("positive_examples", [])])
        out.append(Card(id=c["id"], version=int(c["version"]), data=c, tokens=tokens(text)))
    return tuple(out)


def cards_snapshot(knowledge_dir: Path = KNOWLEDGE_DIR) -> str:
    return _digest([knowledge_dir / "patterns" / "cards.yaml"])


def load_crosswalk(name: str, knowledge_dir: Path = KNOWLEDGE_DIR) -> dict:
    return yaml.safe_load((knowledge_dir / "crosswalks" / f"{name}.yaml").read_text())


def validate_release(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[str]:
    """Return a list of problems; empty means the knowledge release is shippable."""
    problems: list[str] = []
    tax = load_taxonomy(knowledge_dir)
    seen: set[str] = set()
    for card in load_cards(knowledge_dir):
        d = card.data
        if card.id in seen:
            problems.append(f"duplicate card id {card.id}")
        seen.add(card.id)
        for key in ("definition", "label_status", "human_review_status"):
            if not d.get(key):
                problems.append(f"{card.id}: missing {key}")
        if not (d.get("positive_examples") or d.get("negative_examples")):
            problems.append(f"{card.id}: ships with no examples")
        for axis_key, vals in (d.get("axes") or {}).items():
            axis = CARD_AXIS_TO_TAXONOMY.get(axis_key)
            if axis is None:
                problems.append(f"{card.id}: unknown axis key {axis_key}")
                continue
            for v in vals:
                if v not in tax.values(axis):
                    problems.append(f"{card.id}: {v} is not a {axis} value")
        for ref in d.get("source_refs", []):
            if not isinstance(ref, dict) or "source_id" not in ref:
                problems.append(f"{card.id}: source_refs must name a registry source_id")
    for cw in (knowledge_dir / "crosswalks").glob("*.yaml"):
        data = yaml.safe_load(cw.read_text())
        target_axis = data["target_namespace"].split(".")[-1]
        for rel in data["relations"]:
            if rel["relation"] not in {"equivalent", "broader", "narrower", "overlapping", "unmapped"}:
                problems.append(f"{cw.name}: bad relation {rel['relation']}")
            tgt = rel.get("target")
            if tgt is not None and target_axis in tax.axes and tgt not in tax.values(target_axis):
                # satire lives on rhetorical_mode; allow overlap notes to cross axes only when declared
                if not any(tgt in tax.values(a) for a in tax.axes if a not in ("target",)):
                    problems.append(f"{cw.name}: target {tgt} unknown to taxonomy")
            if rel["relation"] == "unmapped" and tgt is not None:
                problems.append(f"{cw.name}: unmapped relation must have null target")
    return problems
