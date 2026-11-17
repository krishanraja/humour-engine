"""The shared analysis core. Every interface calls `analyse` or `compare` here."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from humour_engine import __version__
from humour_engine.analysis.candidate import PROMPT_VERSION, Candidate, Critique
from humour_engine.analysis.context import select_context
from humour_engine.analysis.prompt import (
    CRITIC_SYSTEM,
    PLAIN_SYSTEM,
    SYSTEM,
    build_user_message,
    candidate_tool_schema,
    critique_tool_schema,
    escape_for_block,
)
from humour_engine.analysis.retrieval import retrieve_cards
from humour_engine.analysis.text import input_revision
from humour_engine.analysis.validate import validate_candidate
from humour_engine.contracts.analysis import (
    SUPPORTED_MODALITIES,
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    ComicReading,
    Counterfactual,
    EngineError,
    Modality,
    ResultStatus,
    Segment,
    TaskName,
    TaskResult,
    TaskStatus,
    Usage,
    Versions,
)
from humour_engine.models.providers import (
    AnthropicProvider,
    ControlCenterProvider,
    FixtureProvider,
    Provider,
    ProviderUnavailable,
)
from humour_engine.operations.budget import BudgetExceeded, BudgetLedger, estimate_tokens
from humour_engine.taxonomy import load_taxonomy


@dataclass
class EngineDeps:
    """Injected dependencies. Defaults are safe: no external inference, no persistence."""

    providers: dict[str, Provider] = field(default_factory=dict)
    style_model: object | None = None  # models.style.StyleModel
    profile_store: object | None = None  # profiles.store.ProfileStore
    retrieval_mode: str = "lexical"
    retrieval_blocklist: set[str] = field(default_factory=set)
    max_input_chars: int = 12_000
    second_assessment: str = "off"  # "off" | "auto"
    prompt_variant: str = "engine"  # "plain" (baseline 2) | "ontology" (baseline 3) | "engine"
    max_calls_per_request: int = 4  # server-side clamp on the caller's budget
    cache: object | None = None  # operations.cache.ResultCache

    @classmethod
    def default(cls, *, with_fixture: bool = False, style_model_path: Path | None = None, profile_dir: Path | None = None):
        providers: dict[str, Provider] = {}
        if with_fixture:
            providers["fixture"] = FixtureProvider()
        if AnthropicProvider.available():
            providers["anthropic"] = AnthropicProvider()
        if ControlCenterProvider.available():
            providers["controlcenter"] = ControlCenterProvider()
        style = None
        if style_model_path is not None and style_model_path.exists():
            from humour_engine.models.style import StyleModel

            style = StyleModel.load(style_model_path)
        store = None
        if profile_dir is not None:
            from humour_engine.profiles.store import ProfileStore

            store = ProfileStore(profile_dir)
        return cls(providers=providers, style_model=style, profile_store=store)


def _choose_provider(req: AnalysisRequest, deps: EngineDeps) -> tuple[Provider | None, EngineError | None]:
    allowed = req.provider_policy.allowed_provider_ids
    for pid in allowed:
        p = deps.providers.get(pid)
        if p is None:
            continue
        if p.caps.remote and not req.provider_policy.allow_external_inference:
            continue
        return p, None
    if not allowed:
        return None, EngineError(
            code="no_provider_allowed",
            message="provider allowlist is empty, so no comprehension provider may run",
            task=TaskName.comprehension,
        )
    return None, EngineError(
        code="provider_unavailable",
        message=f"none of the allowed providers {allowed} is configured and permitted for this request",
        task=TaskName.comprehension,
    )


def _material(req: AnalysisRequest, focus: list[Segment], context_segs: list[Segment]) -> dict:
    def seg(s: Segment) -> dict:
        d = {"segment_id": s.segment_id, "speaker_id": s.speaker_id, "text": s.text}
        if s.quoted_from:
            d["quoted_from"] = s.quoted_from
        return d

    c = req.context
    return {
        "focus_segment_ids": [s.segment_id for s in focus],
        "context_segments": [seg(s) for s in context_segs],
        "segments": [seg(s) for s in focus],
        "provided_facts": c.provided_facts,
        "known_references": c.known_references,
        "audience_description": c.audience_description,
        "declared_intent": c.declared_intent,
        "declared_intent_by": c.declared_intent_by,
        "locale": c.locale,
    }


def _call(provider: Provider, ledger: BudgetLedger, system: str, user: str, tool: dict, retry: bool = False):
    est_in = estimate_tokens(system + user + str(tool))
    res = ledger.reserve(est_in, provider.caps.max_output_tokens, retry=retry)
    try:
        resp = provider.interpret(system, user, tool, res.output_tokens)
    except ProviderUnavailable:
        # charges may have been incurred on timeout; the reservation stands
        raise
    ledger.settle(res, resp.input_tokens, resp.output_tokens)
    return resp


def _status(task_results: list[TaskResult]) -> ResultStatus:
    st = [t.status for t in task_results]
    if all(s == TaskStatus.complete for s in st):
        return ResultStatus.complete
    if any(s == TaskStatus.complete for s in st):
        return ResultStatus.partial
    if all(s == TaskStatus.unsupported for s in st):
        return ResultStatus.unsupported
    if all(s in (TaskStatus.abstained, TaskStatus.unsupported) for s in st) and any(s == TaskStatus.abstained for s in st):
        return ResultStatus.abstained
    return ResultStatus.failed


def analyse(req: AnalysisRequest, deps: EngineDeps | None = None, ledger: BudgetLedger | None = None) -> AnalysisResult:
    deps = deps or EngineDeps()
    t0 = time.monotonic()
    tax = load_taxonomy()
    if ledger is None:
        clamped = req.budget.model_copy(
            update={"max_model_calls": min(req.budget.max_model_calls, deps.max_calls_per_request)}
        )
        ledger = BudgetLedger(budget=clamped)
    rev = input_revision(req.model_dump(mode="json", exclude={"request_id", "budget", "provider_policy", "privacy_mode"}))
    analysis_id = "an_" + uuid.uuid4().hex[:16]
    tasks: dict[TaskName, TaskResult] = {}
    errors: list[EngineError] = []
    limitations: list[str] = []
    mode = AnalysisMode.heuristic
    versions = Versions(engine=__version__, taxonomy=tax.version)
    fields: dict = {}

    cache_key = None
    if deps.cache is not None and req.privacy_mode == "retain":
        cache_key = deps.cache.key(req, rev, deps)
        hit = deps.cache.get(cache_key)
        if hit is not None:
            return hit

    unsupported_mod = [s.segment_id for s in req.all_segments().values() if s.modality not in SUPPORTED_MODALITIES]
    processed = {s.modality for s in req.all_segments().values() if s.modality in SUPPORTED_MODALITIES}

    # ---- comprehension. profile_fit and counterfactual depend on it and must request it explicitly,
    # so their outputs never reveal a reading the caller did not ask for.
    needs_semantic = TaskName.comprehension in req.tasks
    validated = None
    selection = select_context(req, deps.max_input_chars)
    fields["truncation"] = selection.truncation
    provider = None
    if needs_semantic:
        sem_status, sem_err = TaskStatus.failed, None
        if unsupported_mod:
            sem_status = TaskStatus.unsupported
            sem_err = EngineError(
                code="unsupported_modality",
                message=f"segments {unsupported_mod} use a modality this release does not process",
                task=TaskName.comprehension,
            )
        elif selection.abstain_reason or selection.truncation.potentially_lost_payoff:
            sem_status = TaskStatus.abstained
            sem_err = EngineError(
                code="context_truncated",
                message=selection.abstain_reason
                or f"omitted context {selection.truncation.omitted_segments} may carry the setup or antecedent",
                task=TaskName.comprehension,
            )
        else:
            provider, perr = _choose_provider(req, deps)
            if provider is None:
                sem_status, sem_err = TaskStatus.unsupported, perr
            else:
                mode = provider.caps.mode
                versions.provider = provider.caps.provider_id
                versions.model = provider.caps.model
                material = _material(req, selection.focus, selection.context)
                if isinstance(provider, FixtureProvider):
                    provider.set_material(material)
                if ledger.price_per_mtok_in is None and provider.caps.price_per_mtok_in is not None:
                    ledger.price_per_mtok_in = provider.caps.price_per_mtok_in
                    ledger.price_per_mtok_out = provider.caps.price_per_mtok_out
                rmode = deps.retrieval_mode if deps.prompt_variant == "engine" else "off"
                cards, snap = retrieve_cards(
                    [s.text for s in selection.focus + selection.context],
                    mode=rmode,
                    blocklist=deps.retrieval_blocklist,
                )
                versions.retrieval_snapshot = snap
                user = build_user_message(material, tax, cards, include_ontology=deps.prompt_variant != "plain")
                system = PLAIN_SYSTEM if deps.prompt_variant == "plain" else SYSTEM
                versions.prompt = f"{PROMPT_VERSION}:{deps.prompt_variant}"
                tool = candidate_tool_schema()
                try:
                    resp = _call(provider, ledger, system, user, tool)
                    try:
                        cand = Candidate.model_validate(resp.payload)
                    except ValidationError as ve:
                        if ledger.remaining_calls() <= 0:
                            raise ProviderUnavailable(
                                "malformed_output", f"provider output failed schema validation: {ve.error_count()} errors"
                            ) from ve
                        problems = "; ".join(
                            f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in ve.errors(include_input=False)[:20]
                        )
                        repair = user + "\n\nYour previous output failed schema validation at: " + problems
                        resp = _call(provider, ledger, system, repair, tool, retry=True)
                        cand = Candidate.model_validate(resp.payload)
                    validated = validate_candidate(cand, req.all_segments(), req.context, tax, processed)
                    errors += validated.errors
                    if not validated.interpretations and cand.interpretations:
                        sem_status = TaskStatus.failed
                        sem_err = EngineError(
                            code="no_valid_interpretation",
                            message="every interpretation failed grounding validation",
                            task=TaskName.comprehension,
                        )
                        validated = None
                    else:
                        sem_status = TaskStatus.complete
                except BudgetExceeded as be:
                    sem_status = TaskStatus.failed
                    sem_err = EngineError(code="budget_exhausted", message=be.reason, task=TaskName.comprehension)
                except ProviderUnavailable as pu:
                    sem_status = TaskStatus.failed
                    sem_err = EngineError(
                        code=pu.code, message=str(pu), task=TaskName.comprehension, retryable=pu.retryable
                    )
                except ValidationError as ve:
                    sem_status = TaskStatus.failed
                    sem_err = EngineError(
                        code="malformed_output",
                        message=f"provider output failed schema validation after repair: {ve.error_count()} errors",
                        task=TaskName.comprehension,
                    )
                except ValueError as ve:
                    # e.g. a malformed reference inside otherwise schema-valid output
                    validated = None
                    sem_status = TaskStatus.failed
                    sem_err = EngineError(
                        code="validation_error", message=f"provider output could not be validated: {ve}"[:300],
                        task=TaskName.comprehension,
                    )

                # bounded second assessment: adds counterevidence, never overrules
                if validated is not None and deps.second_assessment == "auto":
                    uncertain = validated.comic_reading == ComicReading.ambiguous or any(
                        i.uncertainty.score is not None and i.uncertainty.score < 0.6 for i in validated.interpretations
                    )
                    if uncertain and ledger.remaining_calls() > 0:
                        try:
                            cresp = _call(
                                provider,
                                ledger,
                                CRITIC_SYSTEM,
                                user
                                + "\n\n<analysis_under_review>\n"
                                + escape_for_block(cand.model_dump_json())
                                + "\n</analysis_under_review>",
                                critique_tool_schema(),
                            )
                            crit = Critique.model_validate(cresp.payload)
                            for i in validated.interpretations:
                                i.counterevidence += [f"[second assessment] {x}" for x in crit.unsupported_assumptions]
                                i.alternatives += [f"[second assessment] {x}" for x in crit.missed_alternatives]
                            limitations += [f"second assessment flagged evidence: {x}" for x in crit.false_evidence]
                        except (ProviderUnavailable, BudgetExceeded, ValidationError) as e:
                            limitations.append(f"second assessment skipped: {type(e).__name__}")
        if TaskName.comprehension in req.tasks:
            tasks[TaskName.comprehension] = TaskResult(
                task=TaskName.comprehension,
                status=sem_status,
                output_ref="#/interpretations" if sem_status == TaskStatus.complete else None,
                errors=[sem_err] if sem_err else [],
            )
        elif sem_err:
            errors.append(sem_err)

    if validated is not None:
        fields.update(
            comic_reading=validated.comic_reading,
            humour_attempt=validated.humour_attempt,
            interpretations=validated.interpretations,
            evidence=validated.evidence,
            context_dependencies=validated.context_dependencies,
            missing_context=validated.missing_context,
        )
        limitations += validated.limitations

    # ---- styles (source-specific social function classifier)
    if TaskName.styles in req.tasks:
        if deps.style_model is None:
            tasks[TaskName.styles] = TaskResult(
                task=TaskName.styles,
                status=TaskStatus.unsupported,
                errors=[EngineError(code="no_style_model", message="no trained style model is loaded", task=TaskName.styles)],
            )
        else:
            text = " ".join(s.text for s in selection.focus)
            fields["style_prediction"] = deps.style_model.predict_one(text)
            tasks[TaskName.styles] = TaskResult(task=TaskName.styles, status=TaskStatus.complete, output_ref="#/style_prediction")
            if mode == AnalysisMode.heuristic:
                mode = AnalysisMode.local_model

    # ---- attribution
    if TaskName.attribution in req.tasks:
        if deps.style_model is None:
            tasks[TaskName.attribution] = TaskResult(
                task=TaskName.attribution,
                status=TaskStatus.unsupported,
                errors=[
                    EngineError(
                        code="no_attributable_model",
                        message="attribution is only supported for the locally queryable style model",
                        task=TaskName.attribution,
                    )
                ],
            )
        else:
            from humour_engine.attribution.lime import explain

            text = " ".join(s.text for s in selection.focus)
            fields["attributions"] = [explain(deps.style_model, text)]
            tasks[TaskName.attribution] = TaskResult(
                task=TaskName.attribution, status=TaskStatus.complete, output_ref="#/attributions"
            )

    # ---- profile fit
    if TaskName.profile_fit in req.tasks:
        tr, assessment = _profile_fit(req, deps, validated)
        tasks[TaskName.profile_fit] = tr
        if assessment is not None:
            fields["audience_assessment"] = assessment

    # ---- counterfactual
    if TaskName.counterfactual in req.tasks:
        tr, cf = _counterfactual(req, deps, ledger, validated, rev, analysis_id)
        tasks[TaskName.counterfactual] = tr
        if cf is not None:
            fields["counterfactual_analysis"] = cf

    if provider is not None and provider.caps.mode == AnalysisMode.fixture:
        limitations.insert(0, "FIXTURE MODE: hand-authored, unreviewed response for a registered diagnostic input. Not model inference.")
    if ledger.overrun:
        limitations.append("measured usage exceeded the reserved budget on a call; further calls were refused")
    usage = Usage(
        calls=ledger.calls,
        input_tokens=ledger.input_tokens,
        output_tokens=ledger.output_tokens,
        retries=ledger.retries,
        elapsed_ms=int((time.monotonic() - t0) * 1000),
        measured_cost_usd=ledger.cost_usd if (ledger.cost_known and ledger.calls) else None,
        cost_status=("not_applicable" if ledger.calls == 0 or (provider and not provider.caps.remote) else
                     ("estimated" if ledger.cost_known else "unknown")),
    )
    task_list = [tasks[t] for t in req.tasks]
    result = AnalysisResult(
        analysis_id=analysis_id,
        request_id=req.request_id,
        input_revision=rev,
        versions=versions,
        analysis_mode=mode,
        modalities_actually_processed=sorted(processed, key=lambda m: m.value) if not unsupported_mod else [],
        requested_tasks=list(req.tasks),
        task_results=task_list,
        status=_status(task_list),
        usage=usage,
        limitations=limitations,
        errors=errors,
        **fields,
    )
    if cache_key is not None:
        deps.cache.put(cache_key, result)
    return result


def _profile_fit(req: AnalysisRequest, deps: EngineDeps, validated):
    def tr(status, code=None, msg=None):
        errs = [EngineError(code=code, message=msg, task=TaskName.profile_fit)] if code else []
        return TaskResult(task=TaskName.profile_fit, status=status, errors=errs, output_ref=None)

    if not req.taste_profile_id:
        return tr(TaskStatus.unsupported, "no_profile", "profile_fit needs an explicitly supplied taste_profile_id"), None
    if deps.profile_store is None:
        return tr(TaskStatus.unsupported, "no_profile_store", "no profile store is configured"), None
    profile = deps.profile_store.get(req.taste_profile_id)
    if profile is None:
        return tr(TaskStatus.unsupported, "profile_not_found", f"profile {req.taste_profile_id} not found"), None
    if TaskName.comprehension not in req.tasks:
        return tr(TaskStatus.unsupported, "requires_comprehension", "profile_fit requires comprehension in tasks"), None
    if validated is None:
        return tr(TaskStatus.abstained, "no_semantic_result", "profile fit needs a completed comprehension result"), None
    from humour_engine.profiles.assess import assess

    a = assess(profile, validated.interpretations, validated.comic_reading)
    status = TaskStatus.complete if a.fit != "unknown" else TaskStatus.abstained
    t = TaskResult(task=TaskName.profile_fit, status=status, output_ref="#/audience_assessment")
    return t, a


def _counterfactual(req, deps, ledger, validated, rev, analysis_id):
    def tr(status, code=None, msg=None, ref=None):
        errs = [EngineError(code=code, message=msg, task=TaskName.counterfactual)] if code else []
        return TaskResult(task=TaskName.counterfactual, status=status, errors=errs, output_ref=ref)

    if not req.counterfactual_variant:
        return tr(
            TaskStatus.unsupported,
            "no_variant",
            "supply counterfactual_variant; synthetic edit generation is not enabled in this release",
        ), None
    if TaskName.comprehension not in req.tasks:
        return tr(TaskStatus.unsupported, "requires_comprehension", "counterfactual requires comprehension in tasks"), None
    if validated is None:
        return tr(TaskStatus.abstained, "no_semantic_result", "original analysis did not complete"), None
    focus_ids = set(req.focus_segment_ids)
    var_ids = {s.segment_id for s in req.counterfactual_variant}
    if var_ids != focus_ids:
        return tr(TaskStatus.failed, "variant_mismatch", "variant must replace exactly the focus segments"), None
    var_segments = [s for s in req.segments if s.segment_id not in focus_ids] + list(req.counterfactual_variant)
    var_segments.sort(key=lambda s: s.sequence)
    intervention = "; ".join(
        f"{s.segment_id}: '{o.text}' -> '{s.text}'"
        for s in req.counterfactual_variant
        for o in req.segments
        if o.segment_id == s.segment_id
    )
    cf = Counterfactual(
        supplied_or_synthetic="supplied",
        intervention=intervention,
        original_analysis_id=analysis_id,
        original_input_revision=rev,
    )
    if ledger.remaining_calls() <= 0:
        cf.observed_change = None
        return tr(
            TaskStatus.abstained, "budget_exhausted", "shared budget left no call for the variant; observed_change is null"
        ), cf
    var_req = req.model_copy(
        update={
            "request_id": req.request_id + ":variant",
            "segments": var_segments,
            "tasks": [TaskName.comprehension],
            "counterfactual_variant": None,
        }
    )
    var_res = analyse(var_req, deps, ledger)
    cf.variant_analysis_id = var_res.analysis_id
    cf.variant_input_revision = var_res.input_revision
    if var_res.comic_reading is None:
        return tr(
            TaskStatus.failed, "variant_failed", "variant analysis did not complete", None
        ), cf
    a_labels = sorted({v for i in validated.interpretations for vs in i.labels_by_axis.get("mechanism", []) for v in [vs]})
    b_labels = sorted({v for i in var_res.interpretations for v in i.labels_by_axis.get("mechanism", [])})
    cf.observed_change = (
        f"comic_reading {validated.comic_reading.value} -> {var_res.comic_reading.value}; "
        f"mechanisms {a_labels or '[]'} -> {b_labels or '[]'}"
    )
    return tr(TaskStatus.complete, ref="#/counterfactual_analysis"), cf


__all__ = ["EngineDeps", "analyse", "Modality"]
