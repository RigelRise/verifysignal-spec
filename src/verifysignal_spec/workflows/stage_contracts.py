from __future__ import annotations

from typing import Any

from .browser_understanding import browser_first_capability_contract
from .models import StagePayloadValidationFinding, WorkflowStageContract


STAGE_CONTRACTS_SCHEMA = "verifysignal-spec-stage-payload-contracts/v1"

_STAGE_CONTRACTS: dict[str, WorkflowStageContract] = {
    "understand": WorkflowStageContract(
        stage="understand",
        requiredFields=["coverageInventory"],
        optionalFields=[
            "understandingMode",
            "workspaceKind",
            "productSummary",
            "repositorySummary",
            "localStartInstructions",
            "startInstructions",
            "targetEnvironment",
            "targetUrl",
            "url",
            "explorationScope",
            "productSignals",
            "gaps",
            "provenanceTraceabilityStatus",
            "observedAt",
            "git",
            "generatedGitHash",
            "gitAvailable",
            "gitUnavailableReason",
            "gitHash",
            "commitHash",
            "generatedCommitHash",
            "gitBranch",
            "safeInspectionPaths",
            "safePaths",
            "blockedSensitivePaths",
            "validationGoals",
            "knownRuntimeRequirements",
            "candidateUseCases",
            "sourceFilesVisited",
            "partialInventoryReasons",
            "refreshImpacts",
        ],
        defaults={
            "understandingMode": "repository",
            "explorationScope": {
                "maxPagesOrStates": 20,
                "maxDepth": 3,
                "candidateRange": {"minimum": 3, "maximum": 5},
                "softTimeBudgetMinutes": 15,
                "readSafeOnly": True,
            },
        },
        examples=[
            {
                "understandingMode": "browser-first",
                "productSummary": "A project tracking application.",
                "targetEnvironment": {
                    "kind": "live-url",
                    "locator": "https://app.example.test/projects",
                    "reachabilityStatus": "authentication-required",
                    "observedAt": "2026-07-26T18:00:00Z",
                },
                "explorationScope": {
                    "allowedOrigins": ["https://app.example.test"],
                    "status": "complete",
                },
                "productSignals": [
                    {
                        "id": "projects-list",
                        "kind": "surface",
                        "surface": "/projects",
                        "summary": "The signed-in user can view projects.",
                        "evidence": ["A Projects heading was visible."],
                        "provenance": "browser",
                        "observedAt": "2026-07-26T18:00:00Z",
                        "confidence": "high",
                    }
                ],
                "coverageInventory": {
                    "status": "partial",
                    "items": [],
                    "candidateUseCases": [],
                },
            }
        ],
        nextAction="verifysignal workflow persist understand --scope <scope> --payload <payload.json> --json",
    ),
    "specify": WorkflowStageContract(
        stage="specify",
        requiredFields=["surface", "behavior", "expectedOutcome"],
        optionalFields=[
            "alias",
            "title",
            "sourceInventoryItems",
            "customSourceReason",
            "runtimeAssumptions",
            "targetEnvironment",
            "targetSurface",
            "purpose",
            "description",
            "expectedOutcomes",
            "sideEffects",
            "runtimeInputs",
            "runtimeOutputs",
            "resourceIdentity",
            "rerunPolicy",
            "sideEffectLifecycle",
            "credentialReadinessHints",
        ],
        defaults={"status": "draft"},
        examples=[
            {
                "alias": "home-page-unauth",
                "surface": "/",
                "behavior": "Validate the public home page.",
                "expectedOutcome": "Hero, activity, Teams, and Brands sections render.",
                "targetEnvironment": {"kind": "staging-url", "locator": "https://app.example.test"},
                "sideEffects": {"class": "none"},
                "customSourceReason": "Selected by developer.",
            }
        ],
        nextAction="verifysignal workflow persist specify --alias <alias> --payload <payload.json> --json",
    ),
    "clarify": WorkflowStageContract(
        stage="clarify",
        requiredFields=["questions or answers"],
        optionalFields=[
            "alias",
            "questions",
            "answers",
            "sideEffects",
            "runtimeInputs",
            "runtimeOutputs",
            "resourceIdentity",
            "rerunPolicy",
            "sideEffectLifecycle",
            "credentialReadinessHints",
        ],
        examples=[
            {
                "questions": [
                    {
                        "id": "target-environment",
                        "prompt": "Which target environment should be used?",
                        "affects": "runtime",
                        "status": "answered",
                        "answerSummary": "https://app.example.test",
                    }
                ]
            }
        ],
        nextAction="verifysignal workflow persist clarify --alias <alias> --payload <payload.json> --json",
    ),
    "plan": WorkflowStageContract(
        stage="plan",
        requiredFields=["runRequest", "reusableSkills", "runtimeInputs"],
        optionalFields=[
            "alias",
            "mainSkill",
            "supportingSkills",
            "skills",
            "skillReuse",
            "sourceOnlySkills",
            "skillComposition",
            "gateEvidenceMappings",
            "preconditions",
            "validationGates",
            "gateIntentChanges",
            "credentialGroups",
            "credentialRefs",
            "sideEffects",
            "runtimeOutputs",
            "resourceIdentity",
            "rerunPolicy",
            "sideEffectLifecycle",
            "credentialReadinessHints",
            "targetEnvironment",
            "unresolvedBlockingClarifications",
        ],
        defaults={"runRequest": ".verifysignal/run-requests/<alias>.yaml", "runtimeInputs": []},
        examples=[
            {
                "runRequest": ".verifysignal/run-requests/home-page-unauth.yaml",
                "mainSkill": ".verifysignal/skills/validate-home-page-unauth-flow.browser.md",
                "reusableSkills": [".verifysignal/skills/validate-home-page-unauth-flow.browser.md"],
                "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
                "sideEffects": {"class": "none"},
                "validationGates": [{"id": "home-hero-visible", "required": True}],
            }
        ],
        nextAction="verifysignal workflow persist plan --alias <alias> --payload <payload.json> --json",
    ),
    "tasks": WorkflowStageContract(
        stage="tasks",
        requiredFields=["tasks"],
        optionalFields=["alias", "dependencies", "parallelizableGroups"],
        examples=[
            {
                "tasks": [
                    {
                        "id": "T001",
                        "description": "Author the browser skill target map.",
                        "artifact": ".verifysignal/skills/validate-home-page-unauth-flow.browser.md",
                    }
                ]
            }
        ],
        nextAction="verifysignal workflow persist tasks --alias <alias> --payload <payload.json> --json",
    ),
    "implement": WorkflowStageContract(
        stage="implement",
        requiredFields=["runRequest", "skills"],
        optionalFields=[
            "alias",
            "runtimeInputs",
            "runtimeOutputs",
            "sideEffects",
            "resourceIdentity",
            "rerunPolicy",
            "sideEffectLifecycle",
            "credentialReadinessHints",
            "artifactCapabilities",
            "profiles",
            "artifacts",
            "credentialGroups",
            "credentialRefs",
            "skillComposition",
        ],
        examples=[
            {
                "runRequest": {"path": ".verifysignal/run-requests/home-page-unauth.yaml"},
                "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
                "skills": [
                    {
                        "path": ".verifysignal/skills/validate-home-page-unauth-flow.browser.md",
                        "kind": "skill",
                        "intent": {
                            "browser": {
                                "targets": {"page": {"css": "body"}},
                                "steps": [{"id": "open", "action": "navigate", "value": "{{parameters.baseUrl}}/"}],
                                "assertions": [{"id": "page-visible", "kind": "visible", "target": "page", "gateId": "home-hero-visible"}],
                            }
                        },
                    }
                ],
            }
        ],
        nextAction="verifysignal workflow persist implement --alias <alias> --payload <payload.json> --json",
    ),
}

_ALIASES: dict[str, set[str]] = {
    "understand": {"mode", "targetUrl", "url", "safePaths"},
    "specify": {"route", "targetSurface", "purpose", "description", "intent", "expectedOutcomes", "baseUrl", "targetUrl", "url", "stagingUrl", "environmentUrl"},
    "plan": {"skills", "supportingSkills", "mainSkill"},
    "implement": {"artifacts"},
}


class StagePayloadContractError(ValueError):
    def __init__(self, finding: StagePayloadValidationFinding) -> None:
        super().__init__(finding.message)
        self.finding = finding


def stage_contract(stage: str) -> WorkflowStageContract | None:
    return _STAGE_CONTRACTS.get(stage)


def stage_contracts_payload() -> dict[str, Any]:
    contracts = {stage: contract.to_dict() for stage, contract in _STAGE_CONTRACTS.items()}
    return {
        "schemaVersion": STAGE_CONTRACTS_SCHEMA,
        "stages": list(_STAGE_CONTRACTS),
        "byStage": contracts,
        "guidance": (
            "Use these public workflow contracts; do not inspect installed package source to infer payload schemas. "
            "Fresh generated write values preserve the seed plus a run-attempt token. "
            "Resolve `{{parameters.*}}` confirmation expected values before Core execution."
        ),
        "browserFirstUnderstanding": browser_first_capability_contract(),
        "skillExecutionBoundary": {
            "source": "spec-public-workflow-contract",
            "defaultMode": "single-main",
            "rules": [
                "Spec decides the executable run-request skill set before validate/run readiness.",
                "Reusable source skills are authored and preserved outside the executable run-request skill list unless Core declares deterministic multi-skill support.",
                "When Core does not declare multi-skill support, reusable behavior required by the use case must be inlined into the main executable skill.",
                "Gate evidence from source-only skills counts only through explicit composition mapping; otherwise it is supporting or diagnostic.",
            ],
            "planFields": ["mainSkill", "sourceOnlySkills", "skillComposition", "gateEvidenceMappings"],
            "implementFields": ["runRequest", "skills", "skillComposition"],
            "findingCodes": [
                "skill-execution.multiple-unsupported",
                "skill-execution.reusable-marked-executable",
                "skill-execution.legacy-migration-required",
                "skill-execution.gate-evidence-unmapped",
                "skill-execution.source-only-excluded",
            ],
        },
        "writeValueResolution": {
            "generatedFreshness": "Fresh generated write values preserve the seed plus a run-attempt token derived from the prepared run id.",
            "confirmationPlaceholders": "Resolve `{{parameters.*}}` confirmation expected values before Core execution; block missing, credential, unsupported, or secret-looking placeholders.",
            "coreBoundary": "Core receives concrete prepared run-request values, not unresolved Spec placeholders.",
        },
    }


def unsupported_field_warnings(stage: str, payload: dict[str, Any]) -> list[str]:
    contract = stage_contract(stage)
    if not contract:
        return []
    allowed = {"payload", *contract.requiredFields, *contract.optionalFields, *(_ALIASES.get(stage, set()))}
    warnings: list[str] = []
    for key in payload:
        if key not in allowed:
            warnings.append(
                f"Unsupported field '{key}' is not part of stagePayloadContracts.{stage}. "
                f"Review `verifysignal workflow info verifysignal-use-case --json` before persisting this stage."
            )
    return warnings


def missing_required_field_error(stage: str, field: str) -> StagePayloadContractError:
    finding = StagePayloadValidationFinding(
        id=f"{stage}.{field}.missing",
        stage=stage,
        fieldPath=field,
        severity="blocked",
        message=f"Payload missing required public contract field '{field}' for stage '{stage}'.",
        expectedContract=f"stagePayloadContracts.{stage}.requiredFields.{field}",
        recoveryAction="Run `verifysignal workflow info verifysignal-use-case --json` and submit the documented stage payload shape.",
    )
    return StagePayloadContractError(finding)
