"""Compare two variants with one shared aggregate budget."""

from __future__ import annotations

import uuid

from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.analysis import AnalysisRequest, AnalysisResult, EngineError, TaskName
from humour_engine.contracts.compare import CompareRequest, CompareResult, Difference, Variant
from humour_engine.operations.budget import BudgetLedger


def _req(creq: CompareRequest, v: Variant) -> AnalysisRequest:
    return AnalysisRequest(
        request_id=f"{creq.request_id}:{v.label}",
        language=creq.language,
        focus_segment_ids=creq.focus_segment_ids,
        segments=v.segments,
        context=v.context,
        tasks=[TaskName.comprehension],
        provider_policy=creq.provider_policy,
        budget=creq.budget,
    )


def _axis(res: AnalysisResult, axis: str) -> list[str]:
    return sorted({v for i in res.interpretations for v in i.labels_by_axis.get(axis, [])})


def compare(creq: CompareRequest, deps: EngineDeps | None = None) -> CompareResult:
    deps = deps or EngineDeps()
    ledger = BudgetLedger(budget=creq.budget)  # shared: never reset per branch
    errors: list[EngineError] = []
    a = b = None
    try:
        a = analyse(_req(creq, creq.variant_a), deps, ledger)
    except ValueError as e:
        errors.append(EngineError(code="invalid_variant_a", message=str(e)))
    try:
        # same ledger: if a consumed the allowance, b reports budget_exhausted instead of resetting it
        b = analyse(_req(creq, creq.variant_b), deps, ledger)
    except ValueError as e:
        errors.append(EngineError(code="invalid_variant_b", message=str(e)))
    missing = []
    for label, r in (("a", a), ("b", b)):
        if r is None or r.comic_reading is None:
            missing.append(f"variant_{label}: comprehension not available")
    diffs, inv = [], []
    if not missing:
        dims = {
            "comic_reading": (a.comic_reading.value, b.comic_reading.value),
            "mechanisms": (_axis(a, "mechanism"), _axis(b, "mechanism")),
            "rhetorical_modes": (_axis(a, "rhetorical_mode"), _axis(b, "rhetorical_mode")),
            "social_function": (_axis(a, "social_function"), _axis(b, "social_function")),
            "context_dependency": (
                sorted({d.source_kind for d in a.context_dependencies}),
                sorted({d.source_kind for d in b.context_dependencies}),
            ),
            "target": (
                sorted({i.target_and_subject.target for i in a.interpretations}),
                sorted({i.target_and_subject.target for i in b.interpretations}),
            ),
        }
        for d in creq.dimensions:
            va, vb = dims[d]
            if va == vb:
                inv.append(f"{d} unchanged: {va}")
            else:
                grounded = [f"a:{e.evidence_id}" for e in a.evidence] + [f"b:{e.evidence_id}" for e in b.evidence]
                diffs.append(Difference(dimension=d, a=va, b=vb, grounded_in=grounded))
    status = "complete" if not missing else ("partial" if (a or b) else "failed")
    return CompareResult(
        comparison_id="cmp_" + uuid.uuid4().hex[:12],
        request_id=creq.request_id,
        status=status,
        analysis_a=a,
        analysis_b=b,
        differences=diffs,
        invariances=inv,
        missing_components=missing,
        shared_budget_calls_used=ledger.calls,
        errors=errors,
        limitations=["differences are between model analyses; a change in the actual comic mechanism needs human validation"],
    )
