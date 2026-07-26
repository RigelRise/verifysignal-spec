from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from verifysignal_spec.workspace import layout
from verifysignal_spec.workspace.repository import load_document, load_use_case, now_iso
from verifysignal_spec.workspace.validation import looks_secret, validate_no_secret_values

from .models import (
    CandidateValidationUseCase,
    FirstRunCandidate,
    FirstRunCandidateScore,
    FirstRunIdealCriteria,
    FirstRunRecommendation,
    GUIDED_FIRST_RUN_SCHEMA,
    GoldenPathRunState,
    GuidedFirstRunState,
)
from .stage_cards import acceptance_card, blocker_card, build_stage_card, recommendation_card, skip_card
from .repository import load_golden_path_state, save_golden_path_state


GOLDEN_PATH_STATE_SCHEMA = GUIDED_FIRST_RUN_SCHEMA


def classify_first_run_status(
    core_browser_status: str,
    spec_coverage_status: str,
    missing_required_gates: list[str],
    *,
    repaired: bool = False,
) -> tuple[str, bool]:
    if core_browser_status in {"blocked", "error"}:
        return "blocked", False
    if core_browser_status != "passed":
        return "failed", False
    if spec_coverage_status not in {"complete", "passed"} or missing_required_gates:
        return "incomplete", False
    return ("repaired-passed" if repaired else "passed"), True


def score_first_run_candidates(
    candidates: list[CandidateValidationUseCase | FirstRunCandidate],
    *,
    target_status: str = "unknown",
    inventory_status: str = "partial",
) -> list[FirstRunCandidateScore]:
    scored: list[FirstRunCandidateScore] = []
    for candidate in candidates:
        first_run_candidate = (
            candidate if isinstance(candidate, FirstRunCandidate) else FirstRunCandidate.from_candidate_use_case(candidate)
        )
        requirements = [item.lower() for item in first_run_candidate.knownRuntimeRequirements]
        blockers: list[str] = []
        criteria = evaluate_first_run_ideal_criteria(first_run_candidate)
        branch_relevant, branch_reason = detect_branch_relevance(first_run_candidate)
        low_setup = 25 if criteria.publicOrUnauthenticated and criteria.lowExternalDependency else (12 if criteria.noCredentials else 2)
        target = 15 if target_status == "resolved" else 0
        if target_status != "resolved":
            blockers.append("Real target is not resolved.")
        credential_risk = 0 if criteria.noCredentials else -35
        rendered = 20 if criteria.stableRenderedEvidence else 5
        data_risk = 0 if criteria.lowExternalDependency else -20
        freshness = 10 if inventory_status == "complete" else (4 if inventory_status == "partial" else -8)
        read_only = 18 if criteria.readOnly else -28
        single_surface = 10 if criteria.singleVisibleSurface else -12
        priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(first_run_candidate.priority, 2)
        confidence = {"high": 6, "medium": 3, "low": 0}.get(first_run_candidate.confidence, 3)
        raw_score = low_setup + target + rendered + data_risk + freshness + read_only + single_surface + priority + confidence + credential_risk
        score = max(0, min(100, raw_score))
        missing = criteria.missing()
        explicit = bool(missing)
        rationale = _suitability_rationale(first_run_candidate, criteria, blockers)
        scored.append(
            FirstRunCandidateScore(
                candidateAlias=first_run_candidate.alias,
                rank=0,
                score=score,
                lowSetupRisk=low_setup,
                reachableRealTarget=target,
                credentialRisk=credential_risk,
                renderedEvidenceSimplicity=rendered,
                dataDependencyRisk=data_risk,
                inventoryFreshness=freshness,
                rationale=rationale,
                blockers=blockers,
                candidate=first_run_candidate,
                idealCriteriaMet=criteria.met(),
                idealCriteriaMissing=missing,
                requiresExplicitAcceptance=explicit,
                branchRelevant=branch_relevant,
                branchRelevanceReason=branch_reason,
                suitabilityRationale=rationale,
                sourceInventoryItems=list(first_run_candidate.sourceInventoryItems),
            )
        )
    scored.sort(key=lambda item: (item.blockers != [], -item.score, item.candidateAlias))
    for index, item in enumerate(scored, start=1):
        item.rank = index
    return scored


def evaluate_first_run_ideal_criteria(candidate: FirstRunCandidate) -> FirstRunIdealCriteria:
    text = _candidate_text(candidate)
    requirements = " ".join(candidate.knownRuntimeRequirements).lower()
    credential_required = any(_requires_credential(item) for item in [text, requirements])
    read_only = not any(term in text for term in _MUTATING_TERMS)
    single_surface = bool(candidate.surface.strip()) and not any(sep in candidate.surface for sep in ["->", ",", "|"]) and "*" not in candidate.surface
    stable_rendered = _simple_rendered_evidence(candidate) and not _data_dependent(
        [requirements],
        candidate.behavior,
    )
    low_external = not any(term in f"{text} {requirements}" for term in _EXTERNAL_DEPENDENCY_TERMS)
    public = not credential_required and not any(term in text for term in ["protected", "sign-in", "login"])
    safe = public and read_only and single_surface and stable_rendered and low_external
    return FirstRunIdealCriteria(
        publicOrUnauthenticated=public,
        readOnly=read_only,
        singleVisibleSurface=single_surface,
        stableRenderedEvidence=stable_rendered,
        noCredentials=not credential_required,
        lowExternalDependency=low_external,
        safeToAutoGuide=safe,
    )


def detect_branch_relevance(candidate: FirstRunCandidate) -> tuple[bool, str | None]:
    text = _candidate_text(candidate)
    terms = ["active branch", "branch-relevant", "multi-actor", "claim", "request-to-be-added", "add people", "add-people"]
    if any(term in text for term in terms):
        return True, "Candidate appears tied to the active branch or recent feature work."
    return False, None


def build_understanding_onboarding_preparation(*, stage: str = "specify") -> dict[str, Any]:
    next_command = "/verifysignal-understand"
    resume_command = f"/verifysignal-{stage} (resume after `verifysignal workflow check {stage} --json` passes)"
    summary = (
        "Safe product understanding is required before VerifySignal can recommend a reliable first run. "
        "The agent should inspect an available repository or a user-approved live URL, persist secret-safe understanding, "
        "then resume this stage."
    )
    stage_card = build_stage_card(
        stage_id="understanding-auto-prepare",
        title="Prepare Product Understanding",
        status_marker="[RUNNING]",
        summary="Safe understanding can be prepared automatically before first-run selection.",
        why_it_matters="The first recommendation must be grounded in real user-facing surfaces, not guessed from the latest branch.",
        primary_evidence="Missing .verifysignal product context or global understanding.",
        next_action=next_command,
    ).to_dict()
    return {
        "status": "auto-preparable",
        "approvalRequired": False,
        "approvalReason": "",
        "summary": summary,
        "nextCommand": next_command,
        "resumeCommand": resume_command,
        "safetyBoundaries": [
            "Inspect public project structure and non-sensitive source context, or map a user-approved live URL within an explicit read-safe scope.",
            "Do not read local env files, credential stores, cookies, browser storage, or secret-bearing configuration without explicit approval.",
        ],
        "stageCards": [stage_card],
    }


def build_first_run_recommendation(project: Path) -> FirstRunRecommendation:
    context = load_document(layout.product_context_path(project), default={}) or {}
    inventory = context.get("coverageInventory") if isinstance(context.get("coverageInventory"), dict) else {}
    candidates = [
        CandidateValidationUseCase.from_dict(item, str(inventory.get("status", "partial")))
        for item in inventory.get("candidateUseCases", [])
        if isinstance(item, dict)
    ]
    target_status, target_locator = resolve_target_status(context)
    if not candidates:
        return _blocked_recommendation("No coverage inventory candidates were found.", "Run /verifysignal-understand first.")
    ranked = score_first_run_candidates(candidates, target_status=target_status, inventory_status=str(inventory.get("status", "partial")))
    top = next((item for item in ranked if not item.blockers), None)
    if not top and target_status == "resolved" and ranked:
        top = ranked[0]
    if not top or target_status != "resolved":
        code = "unreachable-target" if target_status == "unreachable" else "missing-target"
        blocker = classify_first_run_blocker(code)
        next_action = blocker["nextAction"]
        return FirstRunRecommendation(
            status="blocked",
            targetStatus=target_status,  # type: ignore[arg-type]
            rankedCandidates=[item.to_dict() for item in ranked],
            recommendationText="A reliable real-target first run cannot be recommended yet.",
            acceptancePrompt="Resolve the blocker before accepting a first run.",
            stageCards=blocker["stageCards"],
            nextAction=next_action,
        )
    candidate = top.candidate or FirstRunCandidate(alias=top.candidateAlias, surface="", behavior="")
    explicit_required = bool(top.idealCriteriaMissing)
    recommended = {
        "alias": candidate.alias,
        "candidateAlias": candidate.alias,
        "surface": candidate.surface,
        "behavior": candidate.behavior,
        "score": top.score,
        "rationale": top.rationale,
        "sourceInventoryItems": candidate.sourceInventoryItems,
        "knownRuntimeRequirements": candidate.knownRuntimeRequirements,
        "idealCriteriaMet": list(top.idealCriteriaMet),
        "idealCriteriaMissing": list(top.idealCriteriaMissing),
        "requiresExplicitAcceptance": explicit_required,
        "branchRelevant": top.branchRelevant,
        "branchRelevanceReason": top.branchRelevanceReason,
    }
    next_action = f"verifysignal workflow accept-first-run {candidate.alias} --json"
    inventory_status = str(inventory.get("status", "partial"))
    inventory_note = ""
    if inventory_status in {"partial", "stale"}:
        inventory_note = f" Inventory is {inventory_status}; understanding freshness rules still apply before relying on this recommendation."
    if explicit_required:
        text = (
            f"I recommend {candidate.alias} only as the lowest-risk available first run. "
            f"It is missing ideal criteria: {', '.join(top.idealCriteriaMissing)}.{inventory_note}"
        )
        acceptance_prompt = (
            "Explicit acceptance is required because no candidate meets all ideal first-run criteria. "
            "Accept only if you understand the labeled risk; you can still choose other validations afterward."
        )
    else:
        text = (
            f"I strongly recommend starting with {candidate.alias}. It is the simplest stable real-target validation "
            f"for the first run; after it passes, choose any other deeper use case.{inventory_note}"
        )
        acceptance_prompt = (
            "Accepting this first run is highly recommended so you can see the VerifySignal workflow end to end. "
            "You can choose other validations afterward."
        )
    branch_candidates = [item.to_dict() for item in ranked if item.branchRelevant and item.candidateAlias != candidate.alias]
    return FirstRunRecommendation(
        status="ready",
        targetStatus=target_status,  # type: ignore[arg-type]
        recommendedCandidate=recommended,
        rankedCandidates=[item.to_dict() for item in ranked],
        branchRelevantCandidates=branch_candidates,
        idealCriteria=FirstRunIdealCriteria.from_dict({name: name in top.idealCriteriaMet for name in top.idealCriteriaMet + top.idealCriteriaMissing}).to_dict(),
        explicitAcceptanceRequired=explicit_required,
        recommendationText=text,
        acceptancePrompt=acceptance_prompt,
        stageCards=[
            recommendation_card(
                candidate.alias,
                top.rationale,
                next_action=next_action,
                missing_criteria=top.idealCriteriaMissing,
                branch_relevant_candidates=[item.candidateAlias for item in ranked if item.branchRelevant and item.candidateAlias != candidate.alias],
            )
        ],
        nextAction=next_action,
    )


def accept_first_run(project: Path, alias: str) -> dict[str, Any]:
    record = load_use_case(project, alias)
    next_action = f"verifysignal author {alias} --json"
    state = GuidedFirstRunState(
        selectedCandidate=alias,
        stage="accepted",
        stageStartedAt=now_iso(),
        firstRunStatus="not-started",
        resumeCommand=next_action,
        stageCards=[acceptance_card(alias, next_action=next_action)],
        ownedArtifacts=_owned_artifacts_for_record(record),
        status="accepted",
    ).to_dict()
    state["acceptedAt"] = state["stageStartedAt"]
    state["recommendationStatus"] = "accepted"
    _write_state(project, state)
    return {
        "schemaVersion": GUIDED_FIRST_RUN_SCHEMA,
        "status": "accepted",
        "stage": "accepted",
        "selectedCandidate": alias,
        "selectedCandidateDetails": {
            "alias": record.alias,
            "surface": record.targetSurface,
            "behavior": record.description,
        },
        "firstRunStatus": "not-started",
        "resumeCommand": next_action,
        "stageCards": state["stageCards"],
        "ownedArtifacts": state.get("ownedArtifacts", []),
        "nextAction": next_action,
    }


def skip_first_run(project: Path) -> dict[str, Any]:
    next_action = "Manual selection remains available: use /verifysignal-specify <custom use case> when you are ready."
    skip_meaning = "Skipping records that the golden path was declined; it is not success, failure, or inconclusive."
    state = GuidedFirstRunState(
        selectedCandidate="",
        stage="skipped",
        stageStartedAt=now_iso(),
        firstRunStatus="skipped",
        resumeCommand=next_action,
        stageCards=[skip_card(next_action=next_action)],
        status="skipped",
    ).to_dict()
    state["skippedAt"] = state["stageStartedAt"]
    state["recommendationStatus"] = "skipped"
    _write_state(project, state)
    return {
        "schemaVersion": GUIDED_FIRST_RUN_SCHEMA,
        "status": "skipped",
        "stage": "skipped",
        "firstRunStatus": "skipped",
        "skipMeaning": skip_meaning,
        "resumeCommand": next_action,
        "stageCards": state["stageCards"],
        "nextAction": next_action,
    }


def golden_path_state(project: Path) -> dict[str, Any]:
    return load_golden_path_state(project)


def advance_guided_first_run_state(
    project: Path,
    alias: str,
    *,
    stage: str,
    first_run_status: str | None = None,
    resume_command: str = "",
    summary: str = "",
    status_marker: str | None = None,
    owned_artifacts: list[str] | None = None,
    blocker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = golden_path_state(project)
    if current.get("selectedCandidate") != alias or current.get("recommendationStatus") != "accepted":
        return {}
    marker = status_marker or {
        "authoring": "[RUNNING]",
        "validating": "[RUNNING]",
        "running": "[RUNNING]",
        "repairing": "[REPAIR]",
        "passed": "[PASS]",
        "repaired-passed": "[PASS]",
        "failed": "[FAIL]",
        "blocked": "[BLOCKED]",
    }.get(stage, "[RUNNING]")
    next_action = resume_command or _resume_command_for_stage(alias, stage)
    card_kwargs: dict[str, Any] = {}
    if marker == "[REPAIR]":
        card_kwargs["repair_details"] = summary or "Safe repair is in progress."
    card = build_stage_card(
        stage_id=f"first-run-{stage}",
        title=f"First Run {stage.replace('-', ' ').title()}",
        status_marker=marker,
        summary=summary or f"{alias} is now in {stage}.",
        why_it_matters="The first run remains guided until it reaches pass, repaired-pass, fail, skip, or blocked.",
        primary_evidence=f"Selected candidate: {alias}; stage={stage}",
        next_action=next_action,
        **card_kwargs,
    ).to_dict()
    current.update(
        {
            "schemaVersion": GUIDED_FIRST_RUN_SCHEMA,
            "stage": stage,
            "stageStartedAt": now_iso(),
            "status": stage,
            "firstRunStatus": first_run_status or current.get("firstRunStatus", "not-started"),
            "resumeCommand": next_action,
            "stageCards": [card],
        }
    )
    if owned_artifacts is not None:
        current["ownedArtifacts"] = owned_artifacts
    if blocker is not None:
        current["blocker"] = blocker
    _write_state(project, current)
    return current


def update_golden_path_run_state(project: Path, state: GoldenPathRunState) -> None:
    current = golden_path_state(project)
    guided_stage = _stage_from_first_run_status(state.firstRunStatus)
    resume_command = _resume_command_for_status(state.useCaseAlias, state.firstRunStatus)
    current.update(
        {
            "schemaVersion": GUIDED_FIRST_RUN_SCHEMA,
            "selectedCandidate": current.get("selectedCandidate") or state.useCaseAlias,
            "stage": guided_stage,
            "stageStartedAt": now_iso(),
            "status": guided_stage,
            "runState": state.to_dict(),
            "firstRunStatus": state.firstRunStatus,
            "strictPass": state.strictPass,
            "resumeCommand": resume_command,
            "stageCards": state.stageCards,
        }
    )
    _write_state(project, current)


def summarize_target(value: str) -> str:
    if not value:
        return ""
    if looks_secret(value, "target"):
        return "[redacted-sensitive-target]"
    return value


def summarize_evidence(value: str) -> str:
    if looks_secret(value, "evidence"):
        return "[redacted-sensitive-evidence]"
    text = " ".join(str(value).split())
    return text[:240]


def resolve_target_status(context: dict[str, Any]) -> tuple[str, str | None]:
    target_environment = context.get("targetEnvironment")
    if isinstance(target_environment, dict):
        value = str(target_environment.get("locator") or "")
        reachability = str(target_environment.get("reachabilityStatus") or "unknown")
        if value:
            if looks_secret(value, "target"):
                return "missing", None
            if _looks_fake_or_demo(value):
                return "missing", None
            if reachability == "unreachable" or _looks_unreachable(value):
                return "unreachable", summarize_target(value)
            return "resolved", summarize_target(value)
    for item in context.get("knownRuntimeRequirements", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        value = str(item.get("value") or item.get("default") or "")
        if name in {"baseurl", "target", "targeturl"} and value:
            if looks_secret(value, name):
                return "missing", None
            if _looks_fake_or_demo(value):
                return "missing", None
            if _looks_unreachable(value):
                return "unreachable", summarize_target(value)
            return "resolved", summarize_target(value)
    return "missing", None


def classify_first_run_blocker(code: str, *, alias: str | None = None) -> dict[str, Any]:
    catalog = {
        "missing-target": (
            "missing-target",
            "The first run needs a confirmed real browser target before it can be recommended.",
            "/verifysignal-clarify <alias>",
        ),
        "unreachable-target": (
            "unreachable-target",
            "The selected target is known or likely unreachable from this environment.",
            "Confirm the target URL or start the app, then rerun recommend-first-run.",
        ),
        "unresolved-credentials": (
            "unresolved-credentials",
            "All available candidates require credentials that are not resolved as runtime references.",
            "Choose a public candidate or resolve credential references without persisting values.",
        ),
        "stale-inventory": (
            "stale-inventory",
            "Coverage inventory is stale and cannot support a reliable first-run recommendation.",
            "/verifysignal-understand --scope changed",
        ),
        "stale-workspace": (
            "stale-workspace",
            "Golden Path workspace state is older than the supported schema.",
            "verifysignal workflow inspect-golden-path-state --json",
        ),
        "incompatible-core": (
            "incompatible-core",
            "Configured VerifySignal Core does not expose the required public CLI JSON operations.",
            "verifysignal core setup --json",
        ),
    }
    category, summary, next_action = catalog.get(code, ("unknown-blocker", "The first run is blocked.", "/verifysignal-list"))
    evidence = f"{category}: {summary}"
    return {
        "status": "blocked",
        "category": category,
        "alias": alias,
        "summary": summary,
        "stageCards": [blocker_card("First Run Blocked", summary, evidence, next_action=next_action)],
        "nextAction": next_action,
    }


def _write_state(project: Path, data: dict[str, Any]) -> None:
    findings = validate_no_secret_values(data)
    if findings:
        first = findings[0]
        raise ValueError(f"Secret-looking first-run state value at {first.get('path')}: {first.get('message')}")
    save_golden_path_state(project, data)


def _blocked_recommendation(summary: str, next_action: str) -> FirstRunRecommendation:
    return FirstRunRecommendation(
        status="blocked",
        targetStatus="missing",
        recommendationText="A first run cannot be recommended yet.",
        acceptancePrompt="Resolve the blocker before accepting a first run.",
        stageCards=[blocker_card("First Run Blocked", summary, summary, next_action=next_action)],
        nextAction=next_action,
    )


def _requires_credential(requirement: str) -> bool:
    text = requirement.lower()
    if "unauth" in text or "no auth" in text:
        return False
    return any(term in text for term in ["credential", "password", "authenticated", "protected", "login", "sign-in", "secret", "session"])


_MUTATING_TERMS = [
    "write",
    "writes",
    "add ",
    "add-",
    "create",
    "delete",
    "update",
    "claim",
    "request-to-be-added",
    "invite",
    "billing",
    "payment",
    "stripe",
    "upload",
    "submit",
]


_EXTERNAL_DEPENDENCY_TERMS = [
    "seed",
    "seeded",
    "token",
    "billing",
    "payment",
    "stripe",
    "upload",
    "tus",
    "recaptcha",
    "email",
    "rare data",
    "external service",
    "multiple external",
]


def _simple_rendered_evidence(candidate: FirstRunCandidate) -> bool:
    text = f"{candidate.surface} {candidate.behavior}".lower()
    return any(term in text for term in ["public", "home", "page", "render", "visible", "hero", "table", "content", "search", "list", "unauth"])


def _data_dependent(requirements: list[str], behavior: str) -> bool:
    text = " ".join(requirements + [behavior.lower()])
    return any(term in text for term in ["seed", "seeded", "conditional", "rare data", "empty state", "may be empty"])


def _looks_fake_or_demo(value: str) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or value).lower()
    return any(term in host for term in ["example.com", "demo", "fake", "localhost.demo"])


def _looks_unreachable(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.hostname in {"127.0.0.1", "0.0.0.0"} and parsed.port == 9


def _rationale(candidate: FirstRunCandidate, blockers: list[str]) -> str:
    if blockers:
        return f"{candidate.alias} is blocked for first run: {' '.join(blockers)}"
    return (
        f"{candidate.alias} is suitable because it targets {candidate.surface or 'a real surface'}, "
        f"has {candidate.confidence} confidence, {candidate.priority} priority, and simple rendered evidence."
    )


def _candidate_text(candidate: FirstRunCandidate) -> str:
    return " ".join(
        [
            candidate.alias,
            candidate.surface,
            candidate.behavior,
            candidate.priority,
            candidate.confidence,
            *candidate.knownRuntimeRequirements,
            *candidate.sourceInventoryItems,
        ]
    ).lower()


def _suitability_rationale(candidate: FirstRunCandidate, criteria: FirstRunIdealCriteria, blockers: list[str]) -> str:
    if blockers:
        return f"{candidate.alias} is blocked for first run: {' '.join(blockers)}"
    if criteria.all_met():
        return (
            f"{candidate.alias} is ideal for a first run: public/unauthenticated, read-only, one visible surface, "
            "stable rendered evidence, no credentials, and low external dependency."
        )
    return (
        f"{candidate.alias} is not ideal for a first run because it is missing: {', '.join(criteria.missing())}. "
        "It can be recommended only as the lowest-risk available candidate with explicit acceptance."
    )


def _owned_artifacts_for_record(record: Any) -> list[str]:
    paths: list[str] = []
    if getattr(record, "runRequest", None) and getattr(record.runRequest, "path", ""):
        paths.append(record.runRequest.path)
    if getattr(record, "mainSkill", None) and getattr(record.mainSkill, "path", ""):
        paths.append(record.mainSkill.path)
    for skill in getattr(record, "skills", []) or []:
        path = getattr(skill, "path", "")
        if path and path not in paths:
            paths.append(path)
    return paths


def _stage_from_first_run_status(first_run_status: str) -> str:
    return {
        "passed": "passed",
        "repaired-passed": "repaired-passed",
        "repairing": "repairing",
        "blocked": "blocked",
        "failed": "failed",
        "incomplete": "failed",
        "skipped": "skipped",
    }.get(first_run_status, "running")


def _resume_command_for_status(alias: str, first_run_status: str) -> str:
    if first_run_status in {"passed", "repaired-passed"}:
        return f"verifysignal workflow inspect-golden-path-state --json"
    if first_run_status == "repairing":
        return f"verifysignal repair {alias} --json"
    if first_run_status in {"failed", "incomplete"}:
        return f"verifysignal repair {alias} --json"
    if first_run_status == "blocked":
        return f"verifysignal workflow check run --alias {alias} --json"
    return f"verifysignal run {alias} --json"


def _resume_command_for_stage(alias: str, stage: str) -> str:
    return {
        "authoring": f"verifysignal author {alias} --json",
        "validating": f"verifysignal validate {alias} --runtime-readiness --json",
        "running": f"verifysignal run {alias} --json",
        "repairing": f"verifysignal repair {alias} --json",
        "blocked": f"verifysignal workflow check run --alias {alias} --json",
    }.get(stage, f"verifysignal workflow inspect-golden-path-state --json")
