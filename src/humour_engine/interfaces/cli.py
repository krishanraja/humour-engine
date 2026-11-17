"""Command line: analyse, compare, evaluate, sources, corpus, profile, annotate, serve, mcp, doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from humour_engine.analysis.render import render_compare_markdown, render_markdown
from humour_engine.interfaces.service import REPO_ROOT, build_deps, capabilities, run_analyse, run_compare

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Humour comprehension engine")
sources_app = typer.Typer(no_args_is_help=True, help="Source registry")
evaluate_app = typer.Typer(no_args_is_help=True, help="Evaluation runs")
profile_app = typer.Typer(no_args_is_help=True, help="Taste profiles (explicit feedback only)")
annotate_app = typer.Typer(no_args_is_help=True, help="Human annotation tooling")
app.add_typer(sources_app, name="sources")
app.add_typer(evaluate_app, name="evaluate")
app.add_typer(profile_app, name="profile")
app.add_typer(annotate_app, name="annotate")


def _emit(obj_json: str, md: str, fmt: str) -> None:
    if fmt in ("json", "both"):
        typer.echo(obj_json)
    if fmt in ("markdown", "both"):
        typer.echo(md)


def _providers(fixture: bool, live: bool, controlcenter: bool = False) -> tuple[list[str], bool]:
    ids = []
    if controlcenter:
        ids.append("controlcenter")
    if live:
        ids.append("anthropic")
    if fixture:
        ids.append("fixture")
    return ids, live or controlcenter


@app.command()
def analyse(
    text: list[str] = typer.Option(None, "--text", "-t", help="Focus text; repeat for several turns (last is focus)"),
    request_file: Path = typer.Option(None, "--file", "-f", help="AnalysisRequest JSON"),
    context: list[str] = typer.Option(None, "--context", "-c", help="Earlier turn(s) supplied as context"),
    fact: list[str] = typer.Option(None, "--fact", help="Provided fact"),
    task: list[str] = typer.Option(None, "--task", help="comprehension|styles|attribution|profile_fit|counterfactual"),
    profile: str = typer.Option(None, "--profile"),
    fixture: bool = typer.Option(False, "--fixture", help="Allow the labelled fixture provider"),
    live: bool = typer.Option(False, "--live", help="Allow external inference via the Anthropic adapter"),
    controlcenter: bool = typer.Option(False, "--controlcenter", help="Allow inference through Control Center (engine bearer)"),
    fmt: str = typer.Option("markdown", "--format", help="json|markdown|both"),
):
    deps = build_deps(with_fixture=fixture)
    if request_file:
        payload = json.loads(request_file.read_text())
    else:
        if not text:
            raise typer.BadParameter("give --text or --file")
        segs, seq = [], 0
        for c in context or []:
            segs.append({"segment_id": f"t{seq}", "text": c, "sequence": seq})
            seq += 1
        seq = max(seq, 1)  # focus ids start at t1 so single lines match the fixture pack's ids
        focus = []
        for t in text:
            sid = f"t{seq}"
            segs.append({"segment_id": sid, "text": t, "sequence": seq})
            focus.append(sid)
            seq += 1
        ids, ext = _providers(fixture, live, controlcenter)
        payload = {
            "request_id": "cli",
            "focus_segment_ids": focus[-1:],
            "segments": segs,
            "context": {"provided_facts": fact or []},
            "tasks": list(dict.fromkeys((task or ["comprehension"]) + (["comprehension", "profile_fit"] if profile else []))),
            "taste_profile_id": profile,
            "provider_policy": {"allowed_provider_ids": ids, "allow_external_inference": ext},
        }
    res = run_analyse(payload, deps)
    _emit(res.model_dump_json(indent=1), render_markdown(res), fmt)


@app.command()
def compare(
    request_file: Path = typer.Option(..., "--file", "-f", help="CompareRequest JSON"),
    fixture: bool = typer.Option(False, "--fixture"),
    fmt: str = typer.Option("markdown", "--format"),
):
    res = run_compare(json.loads(request_file.read_text()), build_deps(with_fixture=fixture))
    _emit(res.model_dump_json(indent=1), render_compare_markdown(res), fmt)


@app.command()
def doctor():
    """Check installation, knowledge release, registry and providers. Prints no secrets."""
    from humour_engine.operations.registry import Registry
    from humour_engine.taxonomy import validate_release

    problems = validate_release()
    deps = build_deps(with_fixture=True)
    caps = capabilities(deps)
    rows = Registry().audit()
    typer.echo(f"python: {sys.version.split()[0]}")
    typer.echo(f"knowledge release: {'ok' if not problems else problems}")
    typer.echo(f"registry sources: {len({r['source_id'] for r in rows})}")
    typer.echo(f"style model loaded: {deps.style_model is not None}")
    typer.echo(f"anthropic key present: {caps['anthropic_key_present']}")
    typer.echo(f"providers configured: {sorted(caps['providers_configured'])}")
    if problems:
        raise typer.Exit(1)


@sources_app.command("audit")
def sources_audit(root: list[str] = typer.Option(None, "--root", help="SOURCE_ID=path to verify asset hashes")):
    from humour_engine.operations.registry import Registry

    roots = dict(r.split("=", 1) for r in (root or []))
    rows = Registry().audit({k: Path(v) for k, v in roots.items()})
    for r in rows:
        ops = ",".join(op for op in ("ingestion", "training", "retrieval", "evaluation", "redistribution") if r[op])
        typer.echo(f"{r['source_id']} {r['status']:<15} {str(r['asset']):<52} ops[{ops}] {r.get('verified', '')}")


@evaluate_app.command("diagnostics")
def eval_diagnostics(
    fixture: bool = typer.Option(False, "--fixture"),
    live: bool = typer.Option(False, "--live"),
    out: Path = typer.Option(None, "--out"),
):
    from humour_engine.evaluation.diagnostics import run_pack

    ids, ext = _providers(fixture, live)
    rows = run_pack(build_deps(with_fixture=fixture), ids, ext)
    passed = sum(r["pass"] for r in rows)
    for r in rows:
        typer.echo(f"{'PASS' if r['pass'] else 'FAIL'} {r['case']:<34} {r['mode']:<9} {r['status']:<9} {r['comic_reading']} {r['fails'] or ''}")
    typer.echo(f"{passed}/{len(rows)} passed (mode: {rows[0]['mode'] if rows else 'n/a'})")
    if out:
        out.write_text(json.dumps(rows, indent=1))


@evaluate_app.command("style")
def eval_style(
    s01: Path = typer.Option(..., help="checkout of MaryKenneth/XAI_humour_styles"),
    s02: Path = typer.Option(..., help="checkout of MaryKenneth/Two_Model_Humour_Style"),
    out: Path = typer.Option(REPO_ROOT / "artifacts"),
    run_id: str = typer.Option("style-mk5-v1"),
):
    from humour_engine.evaluation.report import write_style_report
    from humour_engine.evaluation.style_experiment import run

    report = run(s01, s02, out, run_id=run_id)
    path = write_style_report(report, REPO_ROOT / "evals" / "reports")
    typer.echo(f"report: {path}")


@evaluate_app.command("plan-live")
def eval_plan_live(
    isarcasm: Path = typer.Option(None, help="checkout of iabufarha/iSarcasmEval"),
    pairs: int = typer.Option(20),
    out: Path = typer.Option(REPO_ROOT / "evals" / "protocols" / "live_run_plan.json"),
):
    """Prepare the bounded baseline-vs-engine live run. Executes nothing and spends nothing."""
    from humour_engine.evaluation.live_plan import build_plan

    plan = build_plan(isarcasm, pairs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    typer.echo(json.dumps({k: v for k, v in plan.items() if k != "items"}, indent=1))


@profile_app.command("build")
def profile_build(
    feedback: Path = typer.Option(..., help="JSON: {items:[FeedbackItem], pairs:[PairwisePreference]}"),
    profile_id: str = typer.Option(...),
    owner_scope: str = typer.Option(...),
    version: int = typer.Option(1),
    save: bool = typer.Option(False, help="persist the candidate to the profile store (explicit retention)"),
):
    from humour_engine.contracts.profile import FeedbackItem, PairwisePreference
    from humour_engine.interfaces.service import DEFAULT_PROFILE_DIR
    from humour_engine.profiles.build import build_candidate
    from humour_engine.profiles.store import ProfileStore

    data = json.loads(feedback.read_text())
    prof = build_candidate(
        profile_id, owner_scope,
        [FeedbackItem(**i) for i in data.get("items", [])],
        [PairwisePreference(**p) for p in data.get("pairs", [])],
        version=version,
    )
    typer.echo(prof.model_dump_json(indent=1))
    if save:
        typer.echo(f"saved: {ProfileStore(DEFAULT_PROFILE_DIR).save_candidate(prof)}")


@profile_app.command("evaluate")
def profile_evaluate(feedback: Path = typer.Option(...)):
    from humour_engine.contracts.profile import FeedbackItem
    from humour_engine.profiles.evaluate import evaluate_profile

    data = json.loads(feedback.read_text())
    typer.echo(json.dumps(evaluate_profile([FeedbackItem(**i) for i in data.get("items", [])]), indent=1))


@annotate_app.command("export")
def annotate_export(out: Path = typer.Option(REPO_ROOT / "data" / "annotations" / "pilot")):
    from humour_engine.evaluation.annotation import label_studio_config, tasks_from_cases
    from humour_engine.evaluation.diagnostics import load_cases

    out.mkdir(parents=True, exist_ok=True)
    (out / "label_config.xml").write_text(label_studio_config())
    (out / "tasks.json").write_text(json.dumps(tasks_from_cases(load_cases()), indent=1, ensure_ascii=False))
    typer.echo(f"wrote {out}/label_config.xml and tasks.json")


@annotate_app.command("agreement")
def annotate_agreement(export: Path = typer.Option(..., help="Label Studio JSON export")):
    from humour_engine.evaluation.annotation import fleiss_kappa, import_label_studio

    rows = import_label_studio(json.loads(export.read_text()))
    typer.echo(json.dumps(fleiss_kappa(rows), indent=1))


@app.command("schemas")
def schemas(out: Path = typer.Option(REPO_ROOT / "schemas")):
    """Export JSON Schemas for every public contract plus the ontology."""
    from humour_engine.concept import export_schemas

    for p in export_schemas(out):
        typer.echo(str(p))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8765):
    from humour_engine.interfaces.http import serve as _serve

    _serve(host, port)


@app.command()
def mcp():
    from humour_engine.interfaces.mcp_server import main

    main()


if __name__ == "__main__":
    app()
