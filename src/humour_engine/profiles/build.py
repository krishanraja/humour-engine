"""Build a candidate taste profile from explicit feedback only.

Rules derived here are proposals with provenance and support counts. One rejection
never becomes a universal prohibition: low-support rules stay low confidence, and
contradictions are kept as unresolved conflicts. The output is a candidate; it does
not install or overwrite anybody's live rules.
"""

from __future__ import annotations

from collections import defaultdict

from humour_engine.contracts.profile import AxisPreference, FeedbackItem, PairwisePreference, TasteProfile

AXES = ("mechanism", "rhetorical_mode", "social_function", "register", "structure")


def _confidence(support: int, against: int) -> str:
    net = support - against
    if support >= 5 and net >= 4:
        return "high"
    if support >= 3 and net >= 2:
        return "medium"
    return "low"


def build_candidate(
    profile_id: str,
    owner_scope: str,
    items: list[FeedbackItem],
    pairs: list[PairwisePreference] | None = None,
    version: int = 1,
    min_support: int = 2,
) -> TasteProfile:
    pairs = pairs or []
    by_id = {i.item_id: i for i in items}
    pos: dict[tuple[str, str, str | None], list[str]] = defaultdict(list)
    neg: dict[tuple[str, str, str | None], list[str]] = defaultdict(list)
    for it in items:
        bucket = pos if it.judgement == "approved" else neg if it.judgement == "rejected" else None
        if bucket is None:
            continue
        for axis in AXES:
            for v in it.labels_by_axis.get(axis, []):
                bucket[(axis, v, it.context)].append(it.item_id)
    for p in pairs:
        a, b = by_id.get(p.preferred_item_id), by_id.get(p.other_item_id)
        if not a or not b:
            continue
        for axis in AXES:
            av, bv = set(a.labels_by_axis.get(axis, [])), set(b.labels_by_axis.get(axis, []))
            for v in av - bv:
                pos[(axis, v, None)].append(f"{p.pair_id}>")
            for v in bv - av:
                neg[(axis, v, None)].append(f"{p.pair_id}<")
    prefs, conflicts = [], []
    for key in sorted(set(pos) | set(neg), key=lambda k: (k[0], k[1], k[2] or "")):
        axis, v, ctx = key
        s, a = pos.get(key, []), neg.get(key, [])
        if s and a and abs(len(s) - len(a)) <= 1:
            conflicts.append(f"{axis}={v}{' in ' + ctx if ctx else ''}: approved {s} vs rejected {a}")
            continue
        direction = "prefer" if len(s) > len(a) else "avoid"
        support, against = (s, a) if direction == "prefer" else (a, s)
        if len(support) < min_support:
            continue
        prefs.append(
            AxisPreference(
                axis=axis,
                value=v,
                direction=direction,
                support_example_ids=support,
                against_example_ids=against,
                support=len(support),
                confidence=_confidence(len(support), len(against)),
                context=ctx,
            )
        )
    return TasteProfile(
        profile_id=profile_id,
        owner_scope=owner_scope,
        version=version,
        approval_state="candidate",
        preferences=prefs,
        positive_example_ids=[i.item_id for i in items if i.judgement == "approved"],
        disliked_example_ids=[i.item_id for i in items if i.judgement == "rejected"],
        near_miss_example_ids=[i.item_id for i in items if i.judgement == "near_miss"],
        unresolved_conflicts=conflicts,
        built_from_feedback_ids=sorted(by_id) + [p.pair_id for p in pairs],
        notes=[
            "Candidate only. Approval and installation are separate explicit actions by the profile owner.",
            f"Rules need at least {min_support} supporting judgements; single rejections do not become rules.",
            "Items marked 'understood but would not publish' are kept as judgements, not as dislikes of the mechanism."
            if any(i.understood_but_would_not_publish for i in items)
            else "",
        ],
    )
