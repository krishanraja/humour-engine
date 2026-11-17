"""Profile evaluation on feedback withheld from construction.

Agreement with an example already inside a profile is not generalisation. Items are
split by recorded time when available (temporal holdout), else the evaluation is
labelled descriptive. The learned profile is compared with an explicit-rule baseline
(always "unknown") so coverage and accuracy are both visible.
"""

from __future__ import annotations

from humour_engine.contracts.analysis import ComicReading, Interpretation
from humour_engine.contracts.profile import FeedbackItem
from humour_engine.profiles.assess import assess
from humour_engine.profiles.build import build_candidate


def evaluate_profile(items: list[FeedbackItem], holdout_fraction: float = 0.3, min_items: int = 10) -> dict:
    rated = [i for i in items if i.judgement in ("approved", "rejected")]
    if len(rated) < min_items:
        return {"status": "insufficient_feedback", "n": len(rated), "predictive_performance": "unmeasured"}
    timed = all(i.recorded_at for i in rated)
    ordered = sorted(rated, key=lambda i: i.recorded_at) if timed else rated
    cut = int(len(ordered) * (1 - holdout_fraction))
    train, held = ordered[:cut], ordered[cut:]
    prof = build_candidate("eval", "eval", train)
    wins = losses = unknown = 0
    for it in held:
        interp = Interpretation(id="x", literal_reading="", supported_reading="x", labels_by_axis=it.labels_by_axis, is_main=True)
        a = assess(prof, [interp], ComicReading.supported)
        if a.fit in ("unknown", "mixed"):
            unknown += 1
        elif (a.fit == "match") == (it.judgement == "approved"):
            wins += 1
        else:
            losses += 1
    answered = wins + losses
    return {
        "status": "measured" if timed else "descriptive_only",
        "holdout": "temporal" if timed else "order-based (no timestamps): not a predictive claim",
        "n_train": len(train),
        "n_heldout": len(held),
        "correct": wins,
        "incorrect": losses,
        "abstained": unknown,
        "accuracy_when_answered": round(wins / answered, 4) if answered else None,
        "coverage": round(answered / len(held), 4) if held else None,
        "baseline_explicit_rules_only": {"coverage": 0.0, "note": "no learned rules; always unknown"},
    }
