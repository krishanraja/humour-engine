"""Profile fit. Separate from comprehension: it never changes whether a reading is supported."""

from __future__ import annotations

from humour_engine.contracts.analysis import AudienceAssessment, ComicReading, Interpretation, Uncertainty
from humour_engine.contracts.profile import TasteProfile


def assess(profile: TasteProfile, interps: list[Interpretation], reading: ComicReading) -> AudienceAssessment:
    base = dict(profile_id=profile.profile_id, profile_version=profile.version, scope=profile.owner_scope)
    if reading != ComicReading.supported:
        return AudienceAssessment(
            **base, fit="unknown", basis=[f"comic reading is {reading.value}; fit is only assessed for supported readings"],
        )
    if not profile.preferences:
        return AudienceAssessment(**base, fit="unknown", basis=["profile has no supported preferences yet"])
    main = [i for i in interps if i.is_main] or [i for i in interps if i.supported_reading]
    labels = {(axis, v) for i in main for axis, vals in i.labels_by_axis.items() for v in vals}
    hits, misses, support, against = [], [], [], []
    for p in profile.preferences:
        if (p.axis, p.value) in labels:
            note = f"{p.direction} {p.axis}={p.value} ({p.confidence}, support {p.support})"
            (hits if p.direction == "prefer" else misses).append(note)
            (support if p.direction == "prefer" else against).extend(p.support_example_ids)
    if not hits and not misses:
        fit, basis = "unknown", ["no profile preference covers this item's labels"]
    elif hits and not misses:
        fit, basis = "match", hits
    elif misses and not hits:
        fit, basis = "mismatch", misses
    else:
        fit, basis = "mixed", hits + misses
    lims = ["Descriptive rule fit against explicit feedback; predictive accuracy is unmeasured unless a holdout report exists."]
    if profile.approval_state != "approved":
        lims.append(f"profile is {profile.approval_state}, not approved")
    return AudienceAssessment(
        **base,
        fit=fit,
        basis=basis,
        supporting_example_ids=sorted(set(support)),
        conflicting_example_ids=sorted(set(against)),
        uncertainty=Uncertainty(),
        limitations=lims,
    )
