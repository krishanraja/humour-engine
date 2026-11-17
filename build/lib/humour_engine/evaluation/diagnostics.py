"""Diagnostic fixture pack: load cases as requests and check engineering expectations.

These checks prove pipeline behaviour on hand-authored inputs. In fixture mode they
exercise contracts and validators only; they say nothing about comprehension quality.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.analysis import (
    AnalysisRequest,
    AnalysisResult,
    ProviderPolicy,
    Segment,
    TaskName,
)
from humour_engine.models.providers import FIXTURE_PATH


def load_cases(path: Path = FIXTURE_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())["cases"]


def case_request(case: dict, provider_ids: list[str], allow_external: bool = False, tasks=None) -> AnalysisRequest:
    r = case["request"]
    segs = [Segment(**s) for s in r["segments"]]
    return AnalysisRequest(
        request_id=f"diag:{case['id']}",
        focus_segment_ids=r.get("focus") or [s.segment_id for s in segs],
        segments=segs,
        context=r.get("context", {}),
        tasks=tasks or [TaskName.comprehension],
        provider_policy=ProviderPolicy(allowed_provider_ids=provider_ids, allow_external_inference=allow_external),
    )


def check(case: dict, res: AnalysisResult) -> list[str]:
    """Return failed expectations (empty list = pass)."""
    exp, fails = case.get("expect", {}), []
    if res.comic_reading is None:
        return [f"no semantic verdict (status {res.status.value})"]
    cr = res.comic_reading.value
    if "comic_reading" in exp and cr != exp["comic_reading"]:
        fails.append(f"comic_reading {cr} != {exp['comic_reading']}")
    if "comic_reading_in" in exp and cr not in exp["comic_reading_in"]:
        fails.append(f"comic_reading {cr} not in {exp['comic_reading_in']}")
    mechs = {v for i in res.interpretations for v in i.labels_by_axis.get("mechanism", [])}
    if "mechanisms_any" in exp and not (mechs & set(exp["mechanisms_any"])):
        fails.append(f"mechanisms {sorted(mechs)} miss all of {exp['mechanisms_any']}")
    if exp.get("no_main") and any(i.is_main for i in res.interpretations):
        fails.append("declared a main interpretation where none should be")
    kinds = {d.source_kind for d in res.context_dependencies}
    for k in exp.get("context_kinds", []):
        if k not in kinds:
            fails.append(f"missing context dependency kind {k}")
    return fails


def run_pack(deps: EngineDeps, provider_ids: list[str], allow_external: bool = False) -> list[dict]:
    rows = []
    cases = load_cases()
    held_out = {s["text"] for c in cases for s in c["request"]["segments"]}
    deps.retrieval_blocklist = set(deps.retrieval_blocklist) | held_out
    for case in cases:
        req = case_request(case, provider_ids, allow_external)
        res = analyse(req, deps)
        fails = check(case, res) if res.comic_reading is not None else [f"status {res.status.value}"]
        rows.append(
            {
                "case": case["id"],
                "family": case.get("family"),
                "mode": res.analysis_mode.value,
                "status": res.status.value,
                "comic_reading": res.comic_reading.value if res.comic_reading else None,
                "pass": not fails,
                "fails": fails,
                "errors": [e.code for e in res.errors] + [e.code for t in res.task_results for e in t.errors],
            }
        )
    return rows
