from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from verifysignal_spec.core.contracts import PUBLIC_CONTRACT_VERSION, REQUIRED_OPERATIONS
from verifysignal_spec.workspace.models import (
    PostCommitInterpretation,
    ResolvedRuntimeInput,
    RerunPolicy,
    RuntimeOutputDeclaration,
    RuntimeOutputResult,
    SideEffectDeclaration,
)


WorkflowStatus = Literal["not-started", "running", "paused", "blocked", "failed", "completed"]
StageStatus = Literal["pending", "running", "completed", "blocked", "skipped", "failed"]
GateDecisionValue = Literal["approved", "rejected"]
GateConditionEvaluation = Literal["met", "unmet", "not-evaluated"]
GateCoverageStatus = Literal[
    "exercised",
    "missing",
    "incomplete",
    "conditional-met",
    "conditional-unmet",
    "not-applicable",
    "not-evaluated",
    "screenshot-only",
    "network-only",
    "unmapped",
]

WORKFLOW_ID = "verifysignal-use-case"
WORKFLOW_RUN_SCHEMA = "verifysignal-spec-workflow-run/v1"
WORKFLOW_STATE_SCHEMA = "verifysignal-spec-workflow-state/v1"
WORKFLOW_TASK_SET_SCHEMA = "verifysignal-spec-workflow-tasks/v1"
WORKFLOW_ARTIFACT_PLAN_SCHEMA = "verifysignal-spec-workflow-artifact-plan/v1"
WORKFLOW_PREREQUISITE_CHECK_SCHEMA = "verifysignal-spec-workflow-prerequisite-check/v1"
WORKFLOW_CAPABILITY_SCHEMA = "verifysignal-spec-workflow-capability/v1"
WORKFLOW_GUARDRAILS_CAPABILITY = "workflow.guardrails/v1"
WORKFLOW_STAGE_PERSISTENCE_RESULT_SCHEMA = "verifysignal-spec-workflow-stage-persistence-result/v1"
WORKFLOW_VALIDATION_READINESS_SCHEMA = "verifysignal-spec-validation-readiness/v1"
WORKFLOW_MIGRATION_RESULT_SCHEMA = "verifysignal-spec-workflow-migration-result/v1"
CORE_SETUP_SCHEMA = "verifysignal-spec-core-setup/v1"
FIRST_RUN_RECOMMENDATION_SCHEMA = "verifysignal-spec-first-run-recommendation/v1"
GUIDED_FIRST_RUN_SCHEMA = "verifysignal-spec-guided-first-run/v1"
ONBOARDING_GUIDANCE_SCHEMA = "verifysignal-spec-onboarding-guidance/v1"
UNDERSTANDING_ONBOARDING_RESULT_SCHEMA = "verifysignal-spec-understanding-onboarding-result/v1"
GOLDEN_PATH_WORKSPACE_STATE_SCHEMA = "verifysignal-spec-golden-path-workspace-state/v1"
WORKFLOW_UNDERSTANDING_COMMIT_THRESHOLD = 10
WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS = 7
WORKFLOW_STAGES = ["understand", "specify", "clarify", "plan", "tasks", "implement", "validate", "run", "repair"]
COMMAND_STAGES = [*WORKFLOW_STAGES, "list"]


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


@dataclass(slots=True)
class ReadinessBlocker:
    code: str
    severity: Literal["warning", "error", "blocker"] = "blocker"
    category: str | None = None
    message: str = ""
    recoveryCommand: str | None = None
    repairable: bool | None = None
    documentationRef: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReadinessBlocker":
        return cls(
            code=str(data.get("code", "")),
            severity=data.get("severity", "blocker"),
            category=data.get("category"),
            message=str(data.get("message", "")),
            recoveryCommand=data.get("recoveryCommand"),
            repairable=data.get("repairable"),
            documentationRef=data.get("documentationRef"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class WorkflowContractCapability:
    stage: str
    supported: bool = True
    minimumRequiredVersion: str = "0.0.0"
    currentVersion: str | None = None
    missingCommands: list[str] = field(default_factory=list)
    blockers: list[ReadinessBlocker] = field(default_factory=list)
    schemaVersion: str = WORKFLOW_CAPABILITY_SCHEMA
    requiredCapability: str = WORKFLOW_GUARDRAILS_CAPABILITY

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = [item.to_dict() for item in self.blockers]
        return clean(data)


@dataclass(slots=True)
class ManagedWorkspaceArtifact:
    path: str
    kind: str
    schemaVersion: str | None = None
    managed: bool = True
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class StagePersistenceRequest:
    stage: str
    alias: str | None = None
    scope: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StagePersistenceRequest":
        return cls(
            stage=str(data.get("stage", "")),
            alias=data.get("alias"),
            scope=data.get("scope"),
            payload=dict(data.get("payload", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class StagePersistenceResult:
    stage: str
    alias: str | None = None
    status: Literal["persisted", "blocked", "invalid"] = "persisted"
    writtenArtifacts: list[ManagedWorkspaceArtifact] = field(default_factory=list)
    updatedRecords: list[str] = field(default_factory=list)
    blockers: list[ReadinessBlocker] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    nextCommand: str | None = None
    understandingOnboarding: dict[str, Any] | None = None
    schemaVersion: str = WORKFLOW_STAGE_PERSISTENCE_RESULT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["writtenArtifacts"] = [item.to_dict() for item in self.writtenArtifacts]
        data["blockers"] = [item.to_dict() for item in self.blockers]
        return clean(data)


@dataclass(slots=True)
class InventoryPass:
    scope: str
    startedAt: str
    completedAt: str | None = None
    coveredAreas: list[str] = field(default_factory=list)
    uncoveredAreas: list[str] = field(default_factory=list)
    sourceFilesVisited: int = 0
    status: Literal["complete", "partial", "interrupted"] = "partial"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InventoryPass":
        return cls(
            scope=str(data.get("scope", "all")),
            startedAt=str(data.get("startedAt", "")),
            completedAt=data.get("completedAt"),
            coveredAreas=[str(item) for item in data.get("coveredAreas", [])],
            uncoveredAreas=[str(item) for item in data.get("uncoveredAreas", [])],
            sourceFilesVisited=int(data.get("sourceFilesVisited", 0) or 0),
            status=data.get("status", "partial"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class CoverageInventoryItem:
    id: str
    surfaceType: str
    path: str
    title: str
    sourceRefs: list[str] = field(default_factory=list)
    userFacing: bool = True
    inventoryStatus: Literal["covered", "excluded", "stale", "uncovered"] = "covered"
    exclusionReason: str | None = None
    candidateUseCaseRefs: list[str] = field(default_factory=list)
    priority: Literal["critical", "high", "medium", "low"] = "medium"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoverageInventoryItem":
        return cls(
            id=str(data.get("id", "")),
            surfaceType=str(data.get("surfaceType", "route")),
            path=str(data.get("path", "")),
            title=str(data.get("title", "")),
            sourceRefs=[str(item) for item in data.get("sourceRefs", [])],
            userFacing=bool(data.get("userFacing", True)),
            inventoryStatus=data.get("inventoryStatus", "covered"),
            exclusionReason=data.get("exclusionReason"),
            candidateUseCaseRefs=[str(item) for item in data.get("candidateUseCaseRefs", [])],
            priority=data.get("priority", "medium"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class CandidateValidationUseCase:
    alias: str
    surface: str
    behavior: str
    sourceInventoryItems: list[str]
    rationale: str
    confidence: Literal["high", "medium", "low"] = "medium"
    inventorySourceStatus: Literal["complete", "partial", "stale"] = "partial"
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    requiresEnvironment: bool = False
    knownRuntimeRequirements: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], inventory_status: str = "partial") -> "CandidateValidationUseCase":
        alias = str(data.get("alias") or data.get("candidateAlias") or "")
        surface = str(data.get("surface") or data.get("targetSurface") or "")
        source_items = data.get("sourceInventoryItems") or data.get("sourceCoverageItems") or data.get("sourceContext") or []
        return cls(
            alias=alias,
            surface=surface,
            behavior=str(data.get("behavior") or data.get("description") or data.get("title") or ""),
            sourceInventoryItems=[str(item) for item in source_items],
            rationale=str(data.get("rationale") or data.get("description") or data.get("behavior") or ""),
            confidence=data.get("confidence", "medium"),
            inventorySourceStatus=data.get("inventorySourceStatus", inventory_status),
            priority=data.get("priority", "medium"),
            requiresEnvironment=bool(data.get("requiresEnvironment", False)),
            knownRuntimeRequirements=[str(item) for item in data.get("knownRuntimeRequirements", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class CoverageInventory:
    status: Literal["complete", "partial", "stale"] = "partial"
    generatedAt: str = ""
    generatedGitHash: str | None = None
    gitAvailable: bool = False
    sourceFilesVisited: int = 0
    sourceTraceabilityStatus: Literal["complete", "normalized", "missing"] = "missing"
    partialInventoryReasons: list[str] = field(default_factory=list)
    passes: list[InventoryPass] = field(default_factory=list)
    items: list[CoverageInventoryItem] = field(default_factory=list)
    candidateUseCases: list[CandidateValidationUseCase] = field(default_factory=list)
    uncoveredAreas: list[str] = field(default_factory=list)
    staleAreas: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CoverageInventory":
        status = data.get("status", "partial")
        return cls(
            status=status,
            generatedAt=str(data.get("generatedAt", "")),
            generatedGitHash=data.get("generatedGitHash"),
            gitAvailable=bool(data.get("gitAvailable", False)),
            sourceFilesVisited=int(data.get("sourceFilesVisited", 0) or 0),
            sourceTraceabilityStatus=data.get("sourceTraceabilityStatus", "missing"),
            partialInventoryReasons=[str(item) for item in data.get("partialInventoryReasons", [])],
            passes=[InventoryPass.from_dict(item) for item in data.get("passes", [])],
            items=[CoverageInventoryItem.from_dict(item) for item in data.get("items", [])],
            candidateUseCases=[CandidateValidationUseCase.from_dict(item, status) for item in data.get("candidateUseCases", [])],
            uncoveredAreas=[str(item) for item in data.get("uncoveredAreas", [])],
            staleAreas=[str(item) for item in data.get("staleAreas", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["passes"] = [item.to_dict() for item in self.passes]
        data["items"] = [item.to_dict() for item in self.items]
        data["candidateUseCases"] = [item.to_dict() for item in self.candidateUseCases]
        return clean(data)


@dataclass(slots=True)
class MigrationPlan:
    id: str
    reason: str
    affectedArtifacts: list[str]
    proposedActions: list[str]
    destructive: bool = False
    requiresApproval: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MigrationPlan":
        return cls(
            id=str(data.get("id", "")),
            reason=str(data.get("reason", "")),
            affectedArtifacts=[str(item) for item in data.get("affectedArtifacts", [])],
            proposedActions=[str(item) for item in data.get("proposedActions", [])],
            destructive=bool(data.get("destructive", False)),
            requiresApproval=bool(data.get("requiresApproval", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class StructuralWorkspaceValidation:
    status: Literal["pass", "warning", "blocked"] = "pass"
    findings: list[dict[str, Any]] = field(default_factory=list)
    checkedArtifacts: list[str] = field(default_factory=list)
    migrationPlans: list[MigrationPlan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["migrationPlans"] = [item.to_dict() for item in self.migrationPlans]
        return clean(data)


@dataclass(slots=True)
class CoreReadiness:
    status: Literal["available", "missing", "incompatible", "error"] = "missing"
    coreCommand: str | None = None
    version: str | None = None
    contractVersion: str = PUBLIC_CONTRACT_VERSION
    requiredOperations: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"operationName": name, "schemaName": schema, "schemaVersion": version}
            for name, (schema, version) in REQUIRED_OPERATIONS.items()
        ]
    )
    missingOperations: list[str] = field(default_factory=list)
    incompatibleOperations: list[dict[str, Any]] = field(default_factory=list)
    recoveryAction: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requiredOperationsByName"] = {item["operationName"]: item for item in self.requiredOperations}
        return clean(data)


CoreCandidateSource = Literal["explicit", "workspace", "env", "path", "ancestor-sibling"]
CoreCandidateStatus = Literal["missing", "available", "compatible", "incompatible", "error", "skipped"]
CoreSetupStatus = Literal["ready", "missing", "incompatible", "error"]


@dataclass(slots=True)
class CoreCandidateAttempt:
    source: CoreCandidateSource
    command: str
    status: CoreCandidateStatus
    displayPath: str | None = None
    terminal: bool = False
    version: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CoreSetupResult:
    status: CoreSetupStatus
    coreCommand: str | None = None
    source: CoreCandidateSource | None = None
    selectedCandidate: CoreCandidateAttempt | None = None
    persisted: bool = False
    oneTime: bool = False
    version: str | None = None
    contractVersion: str = PUBLIC_CONTRACT_VERSION
    requiredOperations: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"operationName": name, "schemaName": schema, "schemaVersion": version}
            for name, (schema, version) in REQUIRED_OPERATIONS.items()
        ]
    )
    missingOperations: list[str] = field(default_factory=list)
    incompatibleOperations: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[CoreCandidateAttempt] = field(default_factory=list)
    message: str = ""
    nextAction: str = ""
    recoveryCommand: str = "verifysignal core setup --json"
    schemaVersion: str = CORE_SETUP_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selectedCandidate"] = self.selectedCandidate.to_dict() if self.selectedCandidate else None
        data["attempts"] = [attempt.to_dict() for attempt in self.attempts]
        data["requiredOperationsByName"] = {item["operationName"]: item for item in self.requiredOperations}
        return data


@dataclass(slots=True)
class BrowserTargetEnvironment:
    kind: Literal["staging-url", "local-url", "environment-reference"] = "environment-reference"
    locator: str = ""
    sourceStage: Literal["specify", "clarify", "plan", "implement", "validate", "run"] = "specify"
    sourceText: str | None = None
    secretClassification: Literal["non-secret", "sensitive", "unknown"] = "non-secret"
    resolutionStatus: Literal["suggested", "unresolved", "resolved", "stale", "contradictory"] = "unresolved"
    availabilityStatus: Literal["unchecked", "available", "unavailable", "blocked"] = "unchecked"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RuntimePrerequisite:
    id: str
    type: Literal["target-environment", "credential", "test-data", "application-availability", "external-service"] = "target-environment"
    required: bool = True
    status: Literal["unresolved", "resolved", "not-applicable", "blocked"] = "unresolved"
    valueRef: str | None = None
    sourceStage: Literal["specify", "clarify", "plan", "implement", "validate", "run"] = "specify"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RuntimeReadinessCheck:
    useCaseAlias: str
    targetResolutionStatus: Literal["resolved", "unresolved", "stale", "contradictory"] = "unresolved"
    targetReachabilityStatus: Literal["unchecked", "reachable", "unreachable", "blocked"] = "unchecked"
    requiredPrerequisiteStatus: Literal["complete", "missing", "blocked"] = "missing"
    authoringReadinessStatus: Literal["passed", "failed", "blocked", "unchecked"] = "unchecked"
    fullBrowserFlowExecuted: bool = False
    status: Literal["passed", "blocked", "failed"] = "blocked"
    findingIds: list[str] = field(default_factory=list)
    targetLocator: str | None = None
    message: str | None = None
    credentialReadiness: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class StageHandoffDecision:
    key: str
    valueSummary: str
    sourceStage: Literal["specify", "clarify", "plan", "implement", "validate", "run"] = "specify"
    appliesTo: str = ""
    status: Literal["active", "superseded", "stale", "contradictory"] = "active"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class ValidationFinding:
    id: str
    category: Literal[
        "missing-prerequisite",
        "stage-handoff-defect",
        "artifact-structure-defect",
        "selector-or-wait-defect",
        "evidence-mapping-defect",
        "conditional-gate-issue",
        "run-profile-issue",
        "execution-contract-issue",
    ]
    severity: Literal["info", "warning", "blocked", "failed"] = "warning"
    sourceStage: Literal["specify", "clarify", "plan", "implement", "validate", "run", "repair"] = "validate"
    evidence: list[str] = field(default_factory=list)
    recommendedAction: Literal["clarify", "replan", "safe-repair", "confirmed-repair", "rerun", "environment-recovery", "blocked"] = "blocked"
    autoRepairAllowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RepairDecision:
    findingId: str
    action: Literal["clarify", "replan", "safe-repair", "confirmed-repair", "rerun", "environment-recovery", "blocked"] = "blocked"
    requiresUserConfirmation: bool = False
    reason: str = ""
    revalidationRequired: bool = True

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class ConditionalGate:
    gateId: str
    condition: str = ""
    conditionStatus: Literal["unknown", "established-true", "established-false", "not-evaluated"] = "unknown"
    required: bool = False
    evidenceStatus: Literal["missing", "planned", "captured", "not-evaluated"] = "missing"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


WORKFLOW_STAGE_PAYLOAD_CONTRACT_SCHEMA = "verifysignal-spec-stage-payload-contract/v1"


@dataclass(slots=True)
class WorkflowStageContract:
    stage: Literal["specify", "clarify", "plan", "tasks", "implement"]
    requiredFields: list[str] = field(default_factory=list)
    optionalFields: list[str] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)
    unsupportedFieldsPolicy: Literal["reject", "warn", "ignore"] = "warn"
    examples: list[dict[str, Any]] = field(default_factory=list)
    nextAction: str = ""
    errors: list[dict[str, str]] = field(default_factory=list)
    schemaVersion: str = WORKFLOW_STAGE_PAYLOAD_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class StagePayloadValidationFinding:
    id: str
    stage: str
    fieldPath: str
    severity: Literal["info", "warning", "blocked"] = "blocked"
    message: str = ""
    expectedContract: str = ""
    recoveryAction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class ValidationReadinessSummary:
    alias: str
    status: Literal["passed", "failed", "blocked"] = "blocked"
    skillSelectionStatus: Literal["matched", "missing", "ambiguous", "unknown"] = "unknown"
    authoringCoherenceStatus: Literal["passed", "failed", "blocked", "warning", "unchecked"] = "unchecked"
    authoredEvidenceCoverageStatus: Literal["complete", "incomplete", "not-applicable"] = "not-applicable"
    runtimeReadinessStatus: Literal["passed", "failed", "blocked", "not-run"] = "not-run"
    fullBrowserFlowExecuted: bool = False
    nextAction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RunOutcomeSummary:
    alias: str
    overallStatus: Literal["passed", "failed", "incomplete", "blocked"]
    coreBrowserStatus: Literal["passed", "failed", "blocked", "error", "not-run"]
    specCoverageStatus: Literal["passed", "failed", "incomplete", "diagnostic", "complete", "blocked"]
    selectedMainSkill: dict[str, Any] | str | None = None
    profile: str | None = None
    runId: str | None = None
    failedStep: str | None = None
    nextAction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


AgentChatStatusMarker = Literal[
    "[RECOMMENDED]",
    "[ACCEPTED]",
    "[RUNNING]",
    "[PASS]",
    "[REPAIR]",
    "[SKIPPED]",
    "[BLOCKED]",
    "[FAIL]",
]
FirstRunRecommendationStatus = Literal["ready", "blocked", "skipped", "unavailable", "accepted"]
FirstRunStatus = Literal[
    "not-started",
    "skipped",
    "running",
    "passed",
    "repairing",
    "repaired-passed",
    "failed",
    "blocked",
    "incomplete",
    "abandoned",
]


def _reject_stage_card_content(data: dict[str, Any]) -> None:
    from verifysignal_spec.workspace.validation import validate_no_secret_values

    evidence = str(data.get("primaryEvidence", "")).lower()
    if "raw log" in evidence or "raw logs" in evidence:
        raise ValueError("Stage cards must summarize product evidence; raw logs are not valid primary evidence.")
    findings = validate_no_secret_values(data)
    if findings:
        first = findings[0]
        raise ValueError(f"Secret-looking stage-card value at {first.get('path')}: {first.get('message')}")


@dataclass(slots=True)
class AgentChatStageCard:
    stageId: str
    title: str
    statusMarker: AgentChatStatusMarker
    summary: str
    whyItMatters: str
    primaryEvidence: str
    nextAction: str
    repairDetails: str | None = None
    secondaryRefs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        allowed = {
            "[RECOMMENDED]",
            "[ACCEPTED]",
            "[RUNNING]",
            "[PASS]",
            "[REPAIR]",
            "[SKIPPED]",
            "[BLOCKED]",
            "[FAIL]",
        }
        if self.statusMarker not in allowed:
            raise ValueError(f"Unsupported stage-card status marker: {self.statusMarker}")
        missing = [
            name
            for name, value in {
                "stageId": self.stageId,
                "title": self.title,
                "statusMarker": self.statusMarker,
                "summary": self.summary,
                "whyItMatters": self.whyItMatters,
                "primaryEvidence": self.primaryEvidence,
                "nextAction": self.nextAction,
            }.items()
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(f"Stage card missing required field(s): {', '.join(missing)}")
        if self.statusMarker == "[REPAIR]" and not str(self.repairDetails or "").strip():
            raise ValueError("repairDetails is required for [REPAIR] stage cards.")
        _reject_stage_card_content(self.to_dict(validate=False))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentChatStageCard":
        return cls(
            stageId=str(data.get("stageId", "")),
            title=str(data.get("title", "")),
            statusMarker=data.get("statusMarker", "[BLOCKED]"),
            summary=str(data.get("summary", "")),
            whyItMatters=str(data.get("whyItMatters", "")),
            primaryEvidence=str(data.get("primaryEvidence", "")),
            nextAction=str(data.get("nextAction", "")),
            repairDetails=data.get("repairDetails"),
            secondaryRefs=[str(item) for item in data.get("secondaryRefs", [])],
        )

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        data = clean(asdict(self))
        if validate:
            _reject_stage_card_content(data)
        return data


@dataclass(slots=True)
class FirstRunCandidate:
    alias: str
    surface: str
    behavior: str
    sourceInventoryItems: list[str] = field(default_factory=list)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    confidence: Literal["high", "medium", "low"] = "medium"
    requiresEnvironment: bool = False
    knownRuntimeRequirements: list[str] = field(default_factory=list)

    @classmethod
    def from_candidate_use_case(cls, candidate: CandidateValidationUseCase) -> "FirstRunCandidate":
        return cls(
            alias=candidate.alias,
            surface=candidate.surface,
            behavior=candidate.behavior,
            sourceInventoryItems=list(candidate.sourceInventoryItems),
            priority=candidate.priority,
            confidence=candidate.confidence,
            requiresEnvironment=candidate.requiresEnvironment,
            knownRuntimeRequirements=list(candidate.knownRuntimeRequirements),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirstRunCandidate":
        return cls(
            alias=str(data.get("alias", "")),
            surface=str(data.get("surface", "")),
            behavior=str(data.get("behavior", "")),
            sourceInventoryItems=[str(item) for item in data.get("sourceInventoryItems", [])],
            priority=data.get("priority", "medium"),
            confidence=data.get("confidence", "medium"),
            requiresEnvironment=bool(data.get("requiresEnvironment", False)),
            knownRuntimeRequirements=[str(item) for item in data.get("knownRuntimeRequirements", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


IDEAL_FIRST_RUN_CRITERIA = [
    "publicOrUnauthenticated",
    "readOnly",
    "singleVisibleSurface",
    "stableRenderedEvidence",
    "noCredentials",
    "lowExternalDependency",
    "safeToAutoGuide",
]


@dataclass(slots=True)
class FirstRunIdealCriteria:
    publicOrUnauthenticated: bool = False
    readOnly: bool = False
    singleVisibleSurface: bool = False
    stableRenderedEvidence: bool = False
    noCredentials: bool = False
    lowExternalDependency: bool = False
    safeToAutoGuide: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirstRunIdealCriteria":
        return cls(
            publicOrUnauthenticated=bool(data.get("publicOrUnauthenticated", False)),
            readOnly=bool(data.get("readOnly", False)),
            singleVisibleSurface=bool(data.get("singleVisibleSurface", False)),
            stableRenderedEvidence=bool(data.get("stableRenderedEvidence", False)),
            noCredentials=bool(data.get("noCredentials", False)),
            lowExternalDependency=bool(data.get("lowExternalDependency", False)),
            safeToAutoGuide=bool(data.get("safeToAutoGuide", False)),
        )

    def met(self) -> list[str]:
        data = asdict(self)
        return [name for name in IDEAL_FIRST_RUN_CRITERIA if bool(data.get(name))]

    def missing(self) -> list[str]:
        data = asdict(self)
        return [name for name in IDEAL_FIRST_RUN_CRITERIA if not bool(data.get(name))]

    def all_met(self) -> bool:
        return not self.missing()

    def to_dict(self) -> dict[str, Any]:
        data = clean(asdict(self))
        data["met"] = self.met()
        data["missing"] = self.missing()
        return data


@dataclass(slots=True)
class FirstRunSuitabilityScore:
    candidateAlias: str
    rank: int
    score: int
    idealCriteriaMet: list[str] = field(default_factory=list)
    idealCriteriaMissing: list[str] = field(default_factory=list)
    requiresExplicitAcceptance: bool = False
    branchRelevant: bool = False
    branchRelevanceReason: str | None = None
    suitabilityRationale: str = ""
    blockers: list[str] = field(default_factory=list)
    sourceInventoryItems: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirstRunSuitabilityScore":
        return cls(
            candidateAlias=str(data.get("candidateAlias") or data.get("alias") or ""),
            rank=int(data.get("rank", 0) or 0),
            score=int(data.get("score", 0) or 0),
            idealCriteriaMet=[str(item) for item in data.get("idealCriteriaMet", [])],
            idealCriteriaMissing=[str(item) for item in data.get("idealCriteriaMissing", [])],
            requiresExplicitAcceptance=bool(data.get("requiresExplicitAcceptance", False)),
            branchRelevant=bool(data.get("branchRelevant", False)),
            branchRelevanceReason=data.get("branchRelevanceReason"),
            suitabilityRationale=str(data.get("suitabilityRationale") or data.get("rationale") or ""),
            blockers=[str(item) for item in data.get("blockers", [])],
            sourceInventoryItems=[str(item) for item in data.get("sourceInventoryItems", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        data = clean(asdict(self))
        data["alias"] = self.candidateAlias
        return data


GuidedFirstRunStage = Literal[
    "recommended",
    "accepted",
    "authoring",
    "validating",
    "running",
    "repairing",
    "passed",
    "repaired-passed",
    "failed",
    "blocked",
    "skipped",
]


@dataclass(slots=True)
class GuidedFirstRunState:
    selectedCandidate: str
    stage: GuidedFirstRunStage = "recommended"
    stageStartedAt: str = ""
    firstRunStatus: FirstRunStatus = "not-started"
    strictPass: bool = False
    blocker: dict[str, Any] | None = None
    resumeCommand: str = ""
    stageCards: list[dict[str, Any]] = field(default_factory=list)
    ownedArtifacts: list[str] = field(default_factory=list)
    status: Literal["recommended", "accepted", "running", "passed", "skipped", "failed", "blocked"] | None = None
    schemaVersion: str = GUIDED_FIRST_RUN_SCHEMA

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuidedFirstRunState":
        return cls(
            selectedCandidate=str(data.get("selectedCandidate") or data.get("useCaseAlias") or ""),
            stage=data.get("stage", "recommended"),
            stageStartedAt=str(data.get("stageStartedAt", "")),
            firstRunStatus=data.get("firstRunStatus", "not-started"),
            strictPass=bool(data.get("strictPass", False)),
            blocker=data.get("blocker"),
            resumeCommand=str(data.get("resumeCommand") or data.get("nextAction") or ""),
            stageCards=list(data.get("stageCards", [])),
            ownedArtifacts=[str(item) for item in data.get("ownedArtifacts", [])],
            status=data.get("status"),
        )

    def to_dict(self) -> dict[str, Any]:
        allowed_stages = set(GuidedFirstRunStage.__args__)  # type: ignore[attr-defined]
        if self.stage not in allowed_stages:
            raise ValueError(f"Unsupported guided first-run stage: {self.stage}")
        cards = [AgentChatStageCard.from_dict(card).to_dict() for card in self.stageCards]
        data = asdict(self)
        data["stageCards"] = cards
        if not data.get("status"):
            data["status"] = self.stage
        return clean(data)


@dataclass(slots=True)
class OnboardingGuidance:
    integrationKey: str
    terminalTitle: str
    terminalSummary: str
    generatedGuidePath: str
    stageMarkers: list[str] = field(default_factory=list)
    usesColor: bool = True
    plainTextFallback: str = ""
    nextCommand: str = "/verifysignal-specify"
    safetyBoundaries: list[str] = field(default_factory=list)
    successSemantics: list[str] = field(default_factory=list)
    coreStatus: dict[str, Any] | None = None
    schemaVersion: str = ONBOARDING_GUIDANCE_SCHEMA

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OnboardingGuidance":
        return cls(
            integrationKey=str(data.get("integrationKey", "")),
            terminalTitle=str(data.get("terminalTitle", "")),
            terminalSummary=str(data.get("terminalSummary", "")),
            generatedGuidePath=str(data.get("generatedGuidePath", "")),
            stageMarkers=[str(item) for item in data.get("stageMarkers", [])],
            usesColor=bool(data.get("usesColor", True)),
            plainTextFallback=str(data.get("plainTextFallback", "")),
            nextCommand=str(data.get("nextCommand", "/verifysignal-specify")),
            safetyBoundaries=[str(item) for item in data.get("safetyBoundaries", [])],
            successSemantics=[str(item) for item in data.get("successSemantics", [])],
            coreStatus=data.get("coreStatus"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class UnderstandingOnboardingResult:
    status: Literal["complete", "partial", "stale", "blocked", "failed"] = "partial"
    scope: str = "all"
    generatedGitHash: str | None = None
    sourceFilesVisited: int = 0
    candidateCount: int = 0
    trivialCandidateCount: int = 0
    sourceTraceabilityStatus: Literal["complete", "normalized", "missing"] = "missing"
    partialInventoryReasons: list[str] = field(default_factory=list)
    nextAction: str = ""
    schemaVersion: str = UNDERSTANDING_ONBOARDING_RESULT_SCHEMA

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnderstandingOnboardingResult":
        return cls(
            status=data.get("status", "partial"),
            scope=str(data.get("scope", "all")),
            generatedGitHash=data.get("generatedGitHash"),
            sourceFilesVisited=int(data.get("sourceFilesVisited", 0) or 0),
            candidateCount=int(data.get("candidateCount", 0) or 0),
            trivialCandidateCount=int(data.get("trivialCandidateCount", 0) or 0),
            sourceTraceabilityStatus=data.get("sourceTraceabilityStatus", "missing"),
            partialInventoryReasons=[str(item) for item in data.get("partialInventoryReasons", [])],
            nextAction=str(data.get("nextAction", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class FirstRunCandidateScore:
    candidateAlias: str
    rank: int
    score: int
    lowSetupRisk: int = 0
    reachableRealTarget: int = 0
    credentialRisk: int = 0
    renderedEvidenceSimplicity: int = 0
    dataDependencyRisk: int = 0
    inventoryFreshness: int = 0
    rationale: str = ""
    blockers: list[str] = field(default_factory=list)
    candidate: FirstRunCandidate | None = None
    idealCriteriaMet: list[str] = field(default_factory=list)
    idealCriteriaMissing: list[str] = field(default_factory=list)
    requiresExplicitAcceptance: bool = False
    branchRelevant: bool = False
    branchRelevanceReason: str | None = None
    suitabilityRationale: str = ""
    sourceInventoryItems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = clean(asdict(self))
        data["alias"] = self.candidateAlias
        data["scoringSignals"] = {
            "lowSetupRisk": self.lowSetupRisk,
            "reachableRealTarget": self.reachableRealTarget,
            "credentialRisk": self.credentialRisk,
            "renderedEvidenceSimplicity": self.renderedEvidenceSimplicity,
            "dataDependencyRisk": self.dataDependencyRisk,
            "inventoryFreshness": self.inventoryFreshness,
        }
        if self.candidate:
            data["candidate"] = self.candidate.to_dict()
        return clean(data)


@dataclass(slots=True)
class FirstRunRecommendation:
    status: FirstRunRecommendationStatus
    targetStatus: Literal["resolved", "missing", "unreachable", "unknown"] = "unknown"
    recommendedCandidate: dict[str, Any] | None = None
    rankedCandidates: list[dict[str, Any]] = field(default_factory=list)
    branchRelevantCandidates: list[dict[str, Any]] = field(default_factory=list)
    idealCriteria: dict[str, Any] | None = None
    explicitAcceptanceRequired: bool = False
    recommendationText: str = ""
    acceptancePrompt: str = ""
    skipMeaning: str = "Skipping means the golden path was declined; it is not a pass, fail, or inconclusive result."
    stageCards: list[dict[str, Any]] = field(default_factory=list)
    nextAction: str = ""
    schemaVersion: str = FIRST_RUN_RECOMMENDATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        cards = [AgentChatStageCard.from_dict(card).to_dict() for card in self.stageCards]
        data = asdict(self)
        data["stageCards"] = cards
        cleaned = clean(data)
        cleaned.setdefault("recommendedCandidate", self.recommendedCandidate)
        cleaned.setdefault("rankedCandidates", [])
        cleaned.setdefault("branchRelevantCandidates", [])
        cleaned.setdefault("stageCards", [])
        return cleaned


@dataclass(slots=True)
class RepairFeedback:
    repairId: str
    category: str
    autonomy: Literal["auto-applied", "propose-only", "confirmation-required", "blocked"]
    safeMechanical: bool
    before: str
    after: str | None = None
    intentPreserved: bool = False
    confirmationRequired: bool = False
    confirmationRecord: str | None = None
    revalidationStatus: Literal["passed", "failed", "not-run", "blocked"] = "not-run"
    rerunStatus: str | None = None
    nextAction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class GoldenPathRunState:
    useCaseAlias: str
    target: str = ""
    recommendationStatus: Literal["ready", "accepted", "skipped", "blocked"] = "accepted"
    firstRunStatus: FirstRunStatus = "not-started"
    strictPass: bool = False
    coreBrowserStatus: str | None = None
    specCoverageStatus: str | None = None
    missingRequiredGates: list[str] = field(default_factory=list)
    repairFeedback: list[dict[str, Any]] = field(default_factory=list)
    stageCards: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_run_result(
        cls,
        *,
        use_case_alias: str,
        target: str = "",
        core_browser_status: str,
        spec_coverage_status: str,
        missing_required_gates: list[str],
        repaired: bool = False,
        repair_feedback: list[dict[str, Any]] | None = None,
        stage_cards: list[dict[str, Any]] | None = None,
    ) -> "GoldenPathRunState":
        from verifysignal_spec.workflows.first_run import classify_first_run_status

        first_run_status, strict_pass = classify_first_run_status(
            core_browser_status,
            spec_coverage_status,
            missing_required_gates,
            repaired=repaired,
        )
        return cls(
            useCaseAlias=use_case_alias,
            target=target,
            firstRunStatus=first_run_status,
            strictPass=strict_pass,
            coreBrowserStatus=core_browser_status,
            specCoverageStatus=spec_coverage_status,
            missingRequiredGates=list(missing_required_gates),
            repairFeedback=repair_feedback or [],
            stageCards=stage_cards or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class GoldenPathWorkspaceState:
    status: Literal["ready", "blocked", "empty", "untracked", "reset"]
    firstRunStatus: str | None = None
    ownedArtifacts: list[str] = field(default_factory=list)
    preservedArtifacts: list[str] = field(default_factory=list)
    resetPreview: list[str] = field(default_factory=list)
    resumeHint: str | None = None
    warnings: list[str] = field(default_factory=list)
    untrackedRuns: list[dict[str, Any]] | None = None
    nextAction: str = ""
    projectRoot: str | None = None
    firstRunState: dict[str, Any] | None = None
    schemaVersion: str = GOLDEN_PATH_WORKSPACE_STATE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RuntimeFeedbackFinding:
    id: str
    source: Literal["validation", "run", "report-inspection", "screenshot", "workflow-state", "user"] = "run"
    category: Literal[
        "missing-prerequisite",
        "environment-recovery",
        "wait-flow-issue",
        "selector-issue",
        "data-product-state-issue",
        "coverage-mapping-issue",
        "unsupported-feedback",
    ] = "unsupported-feedback"
    severity: Literal["info", "warning", "failed", "blocked"] = "warning"
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    affectedGates: list[str] = field(default_factory=list)
    recommendedAction: Literal["clarify", "plan", "implement-repair", "rerun", "environment-recovery", "blocked"] = "blocked"
    confidence: Literal["low", "medium", "high"] = "low"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RepairConfirmation:
    id: str
    findingId: str
    category: str
    confirmationSource: Literal["direct-user-answer", "clarification", "plan-update", "explicit-command"] = "direct-user-answer"
    confirmationTextSummary: str = ""
    approvedScope: list[str] = field(default_factory=list)
    affectedArtifacts: list[str] = field(default_factory=list)
    revalidationRequired: bool = True
    status: Literal["pending", "applied", "revalidated", "rejected"] = "pending"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class GateIntentState:
    gateId: str
    required: bool = True
    condition: str | None = None
    conditionStatus: Literal["not-applicable", "unknown", "established-true", "established-false", "not-evaluated"] = "not-applicable"
    changeSource: Literal["specify", "clarify", "plan", "repair-confirmation", "migration"] = "plan"
    changeReason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class CorePublicContract:
    contractVersion: str = PUBLIC_CONTRACT_VERSION
    requiredOperations: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"operationName": name, "schemaName": schema, "schemaVersion": version}
            for name, (schema, version) in REQUIRED_OPERATIONS.items()
        ]
    )
    operationName: str | None = None
    schemaName: str | None = None
    schemaVersion: int | None = None
    compatibilityStatus: Literal["compatible", "missing", "incompatible"] = "compatible"
    incompatibilityBehavior: str = ""
    verifysignalVersion: str | None = None
    missingOperations: list[str] = field(default_factory=list)

    @classmethod
    def compatible(cls, verifysignalVersion: str | None = None) -> "CorePublicContract":
        return cls(compatibilityStatus="compatible", verifysignalVersion=verifysignalVersion)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requiredOperationsByName"] = {item["operationName"]: item for item in self.requiredOperations}
        return clean(data)


@dataclass(slots=True)
class WorkflowCommand:
    canonicalName: str
    stage: str
    description: str
    argumentHint: str = ""
    sourceTemplate: str = ""
    integrationInvocation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class WorkflowDefinition:
    workflowId: str = WORKFLOW_ID
    name: str = "VerifySignal Use Case"
    version: str = "1.0.0"
    stages: list[str] = field(default_factory=lambda: WORKFLOW_STAGES.copy())
    gates: list[dict[str, Any]] = field(default_factory=list)
    defaultIntegration: str | None = None
    requiredInputs: list[str] = field(default_factory=lambda: ["goal", "alias"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinition":
        return cls(
            workflowId=str(data.get("workflowId", WORKFLOW_ID)),
            name=str(data.get("name", "VerifySignal Use Case")),
            version=str(data.get("version", "1.0.0")),
            stages=[str(item.get("stage", item)) if isinstance(item, dict) else str(item) for item in data.get("stages", WORKFLOW_STAGES)],
            gates=list(data.get("gates", [])),
            defaultIntegration=data.get("defaultIntegration"),
            requiredInputs=list(data.get("requiredInputs", ["goal", "alias"])),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class WorkflowStageState:
    stage: str
    status: StageStatus = "pending"
    documentPath: str | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    blockers: list[dict[str, Any]] = field(default_factory=list)
    nextCommand: str | None = None
    handoffSummary: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStageState":
        return cls(
            stage=str(data.get("stage", "")),
            status=data.get("status", "pending"),
            documentPath=data.get("documentPath"),
            startedAt=data.get("startedAt"),
            completedAt=data.get("completedAt"),
            blockers=list(data.get("blockers", [])),
            nextCommand=data.get("nextCommand"),
            handoffSummary=data.get("handoffSummary"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class WorkflowGateDecision:
    gateId: str
    stageBefore: str
    decision: GateDecisionValue
    decidedAt: str
    reason: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowGateDecision":
        return cls(
            gateId=str(data.get("gateId", "")),
            stageBefore=str(data.get("stageBefore", "")),
            decision=data.get("decision", "approved"),
            decidedAt=str(data.get("decidedAt", "")),
            reason=data.get("reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class WorkflowRun:
    runId: str
    workflowId: str = WORKFLOW_ID
    useCaseAlias: str = ""
    integration: str | None = None
    status: WorkflowStatus = "paused"
    currentStage: str = "understand"
    startedAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None
    workflowDir: str | None = None
    stageStates: list[WorkflowStageState] = field(default_factory=list)
    gateDecisions: list[WorkflowGateDecision] = field(default_factory=list)
    nextCommand: str | None = None
    resumeCommand: str | None = None
    targetEnvironmentConfirmation: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowRun":
        return cls(
            runId=str(data.get("runId", "")),
            workflowId=str(data.get("workflowId", WORKFLOW_ID)),
            useCaseAlias=str(data.get("useCaseAlias", "")),
            integration=data.get("integration"),
            status=data.get("status", "paused"),
            currentStage=str(data.get("currentStage", "understand")),
            startedAt=data.get("startedAt"),
            updatedAt=data.get("updatedAt"),
            completedAt=data.get("completedAt"),
            workflowDir=data.get("workflowDir"),
            stageStates=[WorkflowStageState.from_dict(item) for item in data.get("stageStates", [])],
            gateDecisions=[WorkflowGateDecision.from_dict(item) for item in data.get("gateDecisions", [])],
            nextCommand=data.get("nextCommand"),
            resumeCommand=data.get("resumeCommand"),
            targetEnvironmentConfirmation=(
                dict(data["targetEnvironmentConfirmation"])
                if isinstance(data.get("targetEnvironmentConfirmation"), dict)
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schemaVersion"] = WORKFLOW_RUN_SCHEMA
        data["stageStates"] = [item.to_dict() for item in self.stageStates]
        data["gateDecisions"] = [item.to_dict() for item in self.gateDecisions]
        return clean(data)


@dataclass(slots=True)
class UseCaseWorkflowReference:
    workflowDir: str
    currentStage: str
    workflowStatus: str
    lastWorkflowRunId: str | None = None
    lastUpdatedAt: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UseCaseWorkflowReference":
        return cls(
            workflowDir=str(data.get("workflowDir", "")),
            currentStage=str(data.get("currentStage", "understand")),
            workflowStatus=str(data.get("workflowStatus", "draft")),
            lastWorkflowRunId=data.get("lastWorkflowRunId"),
            lastUpdatedAt=data.get("lastUpdatedAt"),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class ArtifactPlan:
    useCaseAlias: str
    runRequest: str
    mainSkill: str
    supportingSkills: list[str] = field(default_factory=list)
    sourceOnlySkills: list[str] = field(default_factory=list)
    skillReuse: list[dict[str, Any]] = field(default_factory=list)
    skillComposition: dict[str, Any] | None = None
    gateEvidenceMappings: list[dict[str, Any]] = field(default_factory=list)
    runtimeInputs: list[dict[str, Any]] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    validationGates: list[Any] = field(default_factory=list)
    gateIntentChanges: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactPlan":
        return cls(
            useCaseAlias=str(data.get("useCaseAlias", "")),
            runRequest=str(data.get("runRequest", "")),
            mainSkill=str(data.get("mainSkill", "")),
            supportingSkills=[str(item) for item in data.get("supportingSkills", [])],
            sourceOnlySkills=[str(item) for item in data.get("sourceOnlySkills", [])],
            skillReuse=list(data.get("skillReuse", [])),
            skillComposition=data.get("skillComposition") if isinstance(data.get("skillComposition"), dict) else None,
            gateEvidenceMappings=list(data.get("gateEvidenceMappings", [])),
            runtimeInputs=list(data.get("runtimeInputs", [])),
            preconditions=[str(item) for item in data.get("preconditions", [])],
            validationGates=list(data.get("validationGates", [])),
            gateIntentChanges=list(data.get("gateIntentChanges", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schemaVersion"] = WORKFLOW_ARTIFACT_PLAN_SCHEMA
        return clean(data)


@dataclass(slots=True)
class PlannedValidationGate:
    id: str
    description: str = ""
    required: bool = True
    condition: str | None = None
    conditionEvaluation: GateConditionEvaluation | None = None
    source: str = "plan.validationGates"
    legacy: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannedValidationGate":
        gate_id = str(data.get("id") or data.get("gateId") or "").strip()
        return cls(
            id=gate_id,
            description=str(data.get("description") or data.get("title") or gate_id),
            required=bool(data.get("required", True)),
            condition=str(data.get("condition")).strip() if data.get("condition") else None,
            conditionEvaluation=data.get("conditionEvaluation"),
            source=str(data.get("source") or "plan.validationGates"),
            legacy=bool(data.get("legacy", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RenderedResultAssertion:
    id: str
    gateId: str
    target: str
    kind: str
    expected: Any = None
    domainSemantics: str | None = None
    sourceArtifact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class BackendRequestCheck:
    id: str
    gateId: str
    method: str | None = None
    urlContains: str | None = None
    operationName: str | None = None
    expectedStatus: int | str | None = None
    publicMatchKeys: list[str] = field(default_factory=list)
    sensitiveFieldsExcluded: bool = True
    sourceArtifact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class ScreenshotEvidence:
    id: str
    gateId: str
    name: str | None = None
    sourceArtifact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class EvidenceInventory:
    uiAssertions: list[RenderedResultAssertion] = field(default_factory=list)
    networkChecks: list[BackendRequestCheck] = field(default_factory=list)
    screenshots: list[ScreenshotEvidence] = field(default_factory=list)
    unmappedEvidence: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["uiAssertions"] = [item.to_dict() for item in self.uiAssertions]
        data["networkChecks"] = [item.to_dict() for item in self.networkChecks]
        data["screenshots"] = [item.to_dict() for item in self.screenshots]
        return clean(data)


@dataclass(slots=True)
class GateCoverageResult:
    gateId: str
    status: GateCoverageStatus
    condition: str | None = None
    conditionEvaluation: GateConditionEvaluation | None = None
    uiEvidenceIds: list[str] = field(default_factory=list)
    networkEvidenceIds: list[str] = field(default_factory=list)
    screenshotEvidenceIds: list[str] = field(default_factory=list)
    notes: str | None = None
    required: bool = True
    missingEvidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RuntimeEvidence:
    evidenceId: str
    source: Literal["step", "assertion", "screenshot", "network", "report-summary", "profile-setting"]
    gateId: str | None = None
    status: Literal["passed", "failed", "skipped", "unknown"] = "unknown"
    specificity: Literal["rendered-result", "supporting", "generic"] = "supporting"
    artifactRef: str | None = None
    redactionStatus: Literal["redacted", "not-sensitive", "unknown"] = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RunProfileSettings:
    profile: str
    headed: bool = False
    slowMoMs: int = 0
    source: Literal["default", "run-request", "workspace-profile", "cli-override"] = "default"
    overrides: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class RepairRecommendation:
    id: str
    category: Literal["safe-artifact-repair", "runtime-setup", "replan-required", "clarification-required", "unsupported"]
    runtimeCategory: str | None = None
    safeCategory: Literal[
        "selector-ambiguity",
        "wait-strategy",
        "main-skill-ordering",
        "run-profile-defaults",
        "gateid-mapping",
    ] | None = None
    summary: str = ""
    action: str = ""
    affectedArtifacts: list[str] = field(default_factory=list)
    blockedReason: str | None = None
    requiresUserDecision: bool = False
    sourceFeedback: list[str] = field(default_factory=list)
    autonomy: Literal["auto-applied", "propose-only", "confirmation-required", "blocked"] = "confirmation-required"
    safeMechanical: bool = False
    intentPreserved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class SafeRepairApplication:
    recommendationId: str
    applied: bool = False
    changedArtifacts: list[str] = field(default_factory=list)
    validationStatus: Literal["passed", "failed", "not-run"] = "not-run"
    validationReport: str | None = None
    remainingGaps: list[str] = field(default_factory=list)
    # before/after SHA-256 of each artifact whose bytes actually changed. Present only when
    # `applied` is True: the invariant is that `applied` requires a verified byte mutation.
    beforeSha256: dict[str, str] | None = None
    afterSha256: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class UseCaseValidationResult:
    alias: str
    status: Literal["passed", "incomplete", "failed"]
    coreStatus: str
    coverageStatus: str
    selectedMainSkill: dict[str, Any] | str | None = None
    executedSkill: dict[str, Any] | str | None = None
    skillSelectionStatus: Literal["matched", "mismatch", "unknown"] = "unknown"
    gateCoverage: list[GateCoverageResult] = field(default_factory=list)
    missingRequiredGates: list[str] = field(default_factory=list)
    partialCoverage: list[GateCoverageResult] = field(default_factory=list)
    profileSettings: RunProfileSettings | None = None
    repairRecommendations: list[RepairRecommendation] = field(default_factory=list)
    reportPath: str | None = None
    evidenceDir: str | None = None
    exitCode: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gateCoverage"] = [item.to_dict() for item in self.gateCoverage]
        data["partialCoverage"] = [item.to_dict() for item in self.partialCoverage]
        data["profileSettings"] = self.profileSettings.to_dict() if self.profileSettings else None
        data["repairRecommendations"] = [item.to_dict() for item in self.repairRecommendations]
        return clean(data)


@dataclass(slots=True)
class AuthoringCoherenceResult:
    alias: str
    status: Literal["passed", "warning", "blocked"] = "passed"
    mainSkill: str | None = None
    acceptedArtifactFields: list[str] = field(default_factory=lambda: ["path", "kind", "content", "intent", "browser"])
    normalizedAliases: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gateCoverage: list[GateCoverageResult] = field(default_factory=list)
    schemaVersion: str = "verifysignal-spec-authoring-coherence/v1"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gateCoverage"] = [item.to_dict() for item in self.gateCoverage]
        return clean(data)


@dataclass(slots=True)
class RuntimeContradiction:
    id: str
    gateId: str
    observedEvidence: str
    expectedEvidence: str
    recommendation: Literal["update-target-data", "mark-conditional", "replan"]
    sourceRunId: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class AuthoringTask:
    id: str
    description: str
    artifact: str | None = None
    status: str = "pending"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthoringTask":
        return cls(
            id=str(data.get("id", "")),
            description=str(data.get("description", "")),
            artifact=data.get("artifact"),
            status=str(data.get("status", "pending")),
        )

    def to_dict(self) -> dict[str, Any]:
        return clean(asdict(self))


@dataclass(slots=True)
class AuthoringTaskSet:
    taskSetId: str
    useCaseAlias: str
    sourcePlanPath: str
    planFingerprint: str
    generatedAt: str
    tasks: list[AuthoringTask] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthoringTaskSet":
        return cls(
            taskSetId=str(data.get("taskSetId", "")),
            useCaseAlias=str(data.get("useCaseAlias", "")),
            sourcePlanPath=str(data.get("sourcePlanPath", "")),
            planFingerprint=str(data.get("planFingerprint", "")),
            generatedAt=str(data.get("generatedAt", "")),
            tasks=[AuthoringTask.from_dict(item) for item in data.get("tasks", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schemaVersion"] = WORKFLOW_TASK_SET_SCHEMA
        data["tasks"] = [item.to_dict() for item in self.tasks]
        return clean(data)


def native_invocation(stage: str, style: str = "skill") -> str:
    separator = "-" if style == "skill" else "."
    return f"/verifysignal{separator}{stage}"
