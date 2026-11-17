"""Readable Markdown rendered only from a validated result. Adds no findings."""

from __future__ import annotations

from humour_engine.contracts.analysis import AnalysisMode, AnalysisResult, ComicReading
from humour_engine.contracts.compare import CompareResult


def _ev(res: AnalysisResult, refs: list[str]) -> str:
    by = {e.evidence_id: e for e in res.evidence}
    return ", ".join(f'"{by[r].exact_text}" ({by[r].segment_id}[{by[r].start}:{by[r].end}])' for r in refs if r in by)


def render_markdown(res: AnalysisResult) -> str:
    lines = [f"# Analysis {res.analysis_id}", ""]
    if res.analysis_mode == AnalysisMode.fixture:
        lines += ["> **FIXTURE MODE.** Hand-authored diagnostic response, not model inference.", ""]
    lines.append(
        f"Status: **{res.status.value}** · mode: {res.analysis_mode.value} · "
        f"provider: {res.versions.provider or 'none'} {res.versions.model or ''}".rstrip()
    )
    lines.append("")
    if res.comic_reading is None:
        lines.append("No semantic verdict: comprehension did not complete.")
    else:
        lines.append(f"## Reading: {res.comic_reading.value.replace('_', ' ')}")
        main = [i for i in res.interpretations if i.is_main]
        ordered = main + [i for i in res.interpretations if not i.is_main]
        if res.comic_reading == ComicReading.ambiguous:
            lines.append("Several readings remain credible; none is declared main.")
        for i in ordered:
            tag = " (main)" if i.is_main else ""
            lines.append(f"\n### {i.id}{tag}")
            lines.append(f"- Literal: {i.literal_reading}")
            if i.supported_reading:
                lines.append(f"- Comic reading: {i.supported_reading}")
            if i.connecting_logic:
                lines.append(f"- Mechanism: {i.connecting_logic}")
            labels = "; ".join(f"{k}: {', '.join(v)}" for k, v in i.labels_by_axis.items() if v)
            if labels:
                lines.append(f"- Labels: {labels}")
            if i.evidence_refs:
                lines.append(f"- Evidence: {_ev(res, i.evidence_refs)}")
            if i.alternatives:
                lines.append(f"- Alternatives: {' | '.join(i.alternatives)}")
            if i.counterevidence:
                lines.append(f"- Counterevidence: {' | '.join(i.counterevidence)}")
            u = i.uncertainty
            lines.append(f"- Confidence: {u.score if u.score is not None else 'unknown'} ({u.score_kind})")
        if res.context_dependencies:
            lines.append("\n## Context the reading relies on")
            for d in res.context_dependencies:
                lines.append(f"- [{d.source_kind}, {d.verification_status}] {d.claim}")
        if res.missing_context:
            lines.append("\n## Missing context")
            lines += [f"- {m}" for m in res.missing_context]
    if res.style_prediction:
        sp = res.style_prediction
        lines.append("\n## Social-function classifier (source-specific, not comprehension)")
        lines.append(f"- {sp.model}: {sp.predicted} ({sp.uncertainty.score_kind} {sp.uncertainty.score:.2f})")
    for a in res.attributions:
        lines.append(f"\n## Model attribution ({a.method}, fidelity {a.fidelity})")
        lines.append("Explains the classifier's sensitivity, not why a person finds the text funny.")
        lines += [f"- {w}: {v:+.3f}" for w, v in a.features[:8]]
    if res.audience_assessment:
        aa = res.audience_assessment
        lines.append(f"\n## Audience fit (profile {aa.profile_id} v{aa.profile_version}, {aa.score_kind})")
        lines.append(f"- Fit: {aa.fit}; basis: {'; '.join(aa.basis)}")
    if res.counterfactual_analysis:
        cf = res.counterfactual_analysis
        lines.append(f"\n## Counterfactual ({cf.supplied_or_synthetic})")
        lines.append(f"- Intervention: {cf.intervention}")
        lines.append(f"- Observed change: {cf.observed_change or 'not observed'}")
    lines.append("\n## Tasks")
    for t in res.task_results:
        extra = "; ".join(f"{e.code}: {e.message}" for e in t.errors)
        lines.append(f"- {t.task.value}: {t.status.value}" + (f" ({extra})" if extra else ""))
    if res.truncation.occurred:
        lines.append(f"\nTruncation: omitted {res.truncation.omitted_segments}")
    u = res.usage
    lines.append(
        f"\nUsage: {u.calls} calls, {u.input_tokens} in / {u.output_tokens} out tokens, "
        f"{u.retries} retries, {u.elapsed_ms} ms, cost {u.measured_cost_usd if u.measured_cost_usd is not None else u.cost_status}"
    )
    if res.limitations:
        lines.append("\n## Limitations")
        lines += [f"- {x}" for x in res.limitations]
    if res.errors:
        lines.append("\n## Errors")
        lines += [f"- {e.code}: {e.message}" for e in res.errors]
    return "\n".join(lines) + "\n"


def render_compare_markdown(cr: CompareResult) -> str:
    lines = [f"# Comparison {cr.comparison_id}", "", f"Status: **{cr.status}** · shared calls used: {cr.shared_budget_calls_used}"]
    for d in cr.differences:
        lines.append(f"- **{d.dimension}** changed: {d.a} -> {d.b}")
    for i in cr.invariances:
        lines.append(f"- {i}")
    for m in cr.missing_components:
        lines.append(f"- missing: {m}")
    for x in cr.limitations:
        lines.append(f"\n_{x}_")
    return "\n".join(lines) + "\n"
