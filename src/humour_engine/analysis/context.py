"""Context selection under an explicit size policy.

Policy: focus segments are never cut. Context segments are kept nearest-first
(by sequence) until the character budget is used. If a focus segment alone does
not fit, the analysis abstains rather than judging a fragment. Any omission is
reported; omitted context that precedes the focus is flagged as a possible lost
setup or antecedent.
"""

from __future__ import annotations

from dataclasses import dataclass

from humour_engine.contracts.analysis import AnalysisRequest, Segment, Truncation


@dataclass
class Selection:
    focus: list[Segment]
    context: list[Segment]
    truncation: Truncation
    abstain_reason: str | None = None


def select_context(req: AnalysisRequest, max_chars: int) -> Selection:
    focus_ids = set(req.focus_segment_ids)
    focus = [s for s in req.segments if s.segment_id in focus_ids]
    others = [s for s in req.segments if s.segment_id not in focus_ids] + list(req.context.prior_segments)
    used = sum(len(s.text) for s in focus) + sum(len(f) for f in req.context.provided_facts)
    if used > max_chars:
        return Selection(
            focus=focus,
            context=[],
            truncation=Truncation(
                occurred=True, omitted_segments=[s.segment_id for s in others], potentially_lost_payoff=True
            ),
            abstain_reason="focus material exceeds the analysable size; refusing to judge a fragment",
        )
    first_focus_seq = min(s.sequence for s in focus)
    # nearest to the focus first; prior segments without a sequence relation sort by their own sequence
    others_sorted = sorted(others, key=lambda s: abs(s.sequence - first_focus_seq))
    kept, omitted = [], []
    for s in others_sorted:
        if used + len(s.text) <= max_chars:
            kept.append(s)
            used += len(s.text)
        else:
            omitted.append(s)
    kept.sort(key=lambda s: s.sequence)
    lost = any(s.sequence < first_focus_seq for s in omitted) or any(
        s.segment_id in {o.segment_id for o in omitted} for s in req.context.prior_segments
    )
    return Selection(
        focus=focus,
        context=kept,
        truncation=Truncation(
            occurred=bool(omitted),
            omitted_segments=[s.segment_id for s in omitted],
            potentially_lost_payoff=bool(omitted) and lost,
        ),
    )
