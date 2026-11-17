"""Lexical retrieval of approved pattern cards.

Starts deliberately small. It must beat a no-retrieval baseline before it earns a
default place; `mode="off"` is the ablation. It never returns an example that is
the analysed input itself, and evaluation runs pass a blocklist of held-out texts.
"""

from __future__ import annotations

from humour_engine.analysis.text import normalise_for_identity
from humour_engine.taxonomy import Card, cards_snapshot, load_cards, tokens


def retrieve_cards(
    texts: list[str],
    k: int = 3,
    mode: str = "lexical",
    blocklist: set[str] | None = None,
) -> tuple[list[Card], str | None]:
    if mode == "off":
        return [], None
    query = frozenset().union(*(tokens(t) for t in texts)) if texts else frozenset()
    inputs = {normalise_for_identity(t) for t in texts}
    blocked = inputs | {normalise_for_identity(b) for b in (blocklist or set())}
    scored = []
    for card in load_cards():
        examples = [str(x) for x in card.data.get("positive_examples", []) + card.data.get("negative_examples", [])]
        if any(normalise_for_identity(e) in blocked for e in examples):
            # never hand the model the same item (or a held-out item) with its stored label
            continue
        overlap = len(query & card.tokens)
        if overlap:
            scored.append((overlap, card.id, card))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [c for _, _, c in scored[:k]], f"cards@{cards_snapshot()}"
