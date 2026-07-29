from __future__ import annotations

from dataclasses import asdict, field
from typing import Any, Literal

try:  # Pydantic-backed dataclasses when the planned dependency is installed.
    from pydantic.dataclasses import dataclass
except Exception:  # pragma: no cover - fallback for minimal bootstrap envs
    from dataclasses import dataclass


Status = Literal["draft", "ready", "blocked", "failed", "deprecated", "unknown"]
CoreStatus = Literal["passed", "failed", "blocked", "error"]
SideEffectClass = Literal["none", "authenticated-read", "write", "external-notification", "unknown"]
SideEffectPolicyMode = Literal["observe", "warn", "enforce"]
RerunDecision = Literal["allowed", "allowed-with-new-inputs", "requires-confirmation", "blocked"]
ResourceIdentityStrategy = Literal["generated-input", "provided-input", "post-commit-binding", "manual-confirmation"]
CollisionPolicy = Literal["avoid", "allow-duplicates", "requires-confirmation"]
ResourceIdentityConfidence = Literal["high", "confirmed", "unknown"]
ReadinessCurrentStatus = Literal["ready", "not-checked", "stale", "needs-validate", "blocked", "unknown"]
ImpactStatus = Literal["unaffected", "affected", "unknown"]
CleanupPolicy = Literal["none", "manual", "automated", "external", "not-declared"]
CapabilitySeverity = Literal["info", "warning", "confirmation", "blocker"]
UnderstandingStatus = Literal["current", "stale", "unknown"]
UnderstandingPolicy = Literal["block", "warn", "requires-confirmation", "allow"]
ResolvedBindingStatus = Literal["prepared", "committed", "discarded"]


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


@dataclass(slots=True)
class PolicyCompatibilityFinding:
    code: str
    severity: str
    path: str
    message: str
    migrationAvailable: bool = False
    guidedChoices: list[dict[str, str]] = field(default_factory=list)
    blocksExecution: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ConfirmationSignalSupport:
    signalType: str
    staticSupport: bool = False
    runtimeSupport: bool | None = None
    effectiveSupport: bool = False
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class SupersedeReview:
    reviewId: str
    sourceRunId: str
    ownerDecision: str
    evidenceSummary: str
    previousClassification: dict[str, Any]
    resultingClassification: dict[str, Any]
    reason: str
    createdAt: str
    createdBy: str | None = None
    schemaVersion: str = "verifysignal-spec-supersede-review/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SupersedeReview":
        return cls(
            reviewId=str(data.get("reviewId", "")),
            sourceRunId=str(data.get("sourceRunId", "")),
            ownerDecision=str(data.get("ownerDecision", "")),
            evidenceSummary=str(data.get("evidenceSummary", "")),
            previousClassification=dict(data.get("previousClassification", {})),
            resultingClassification=dict(data.get("resultingClassification", {})),
            reason=str(data.get("reason", "")),
            createdAt=str(data.get("createdAt", "")),
            createdBy=data.get("createdBy"),
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-supersede-review/v1")),
        )

    def validate(self) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        required = {
            "reviewId": self.reviewId,
            "sourceRunId": self.sourceRunId,
            "ownerDecision": self.ownerDecision,
            "evidenceSummary": self.evidenceSummary,
            "reason": self.reason,
            "createdAt": self.createdAt,
        }
        for field_name, value in required.items():
            if not str(value or "").strip():
                findings.append(
                    {
                        "severity": "blocking",
                        "code": "supersede-review-field-missing",
                        "path": f"supersedeReview.{field_name}",
                        "message": f"Supersede review requires {field_name}.",
                    }
                )
        if not self.previousClassification:
            findings.append({"severity": "blocking", "code": "supersede-review-previous-missing", "path": "supersedeReview.previousClassification", "message": "Supersede review requires previousClassification."})
        if not self.resultingClassification:
            findings.append({"severity": "blocking", "code": "supersede-review-resulting-missing", "path": "supersedeReview.resultingClassification", "message": "Supersede review requires resultingClassification."})
        return findings

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RerunPolicy:
    afterNoCommit: RerunDecision = "allowed"
    afterCommit: RerunDecision = "blocked"
    afterUnknown: RerunDecision = "requires-confirmation"
    refreshRuntimeInputs: list[str] = field(default_factory=list)
    notes: str | None = None
    legacyFindings: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RerunPolicy":
        data = data if isinstance(data, dict) else {}
        refresh_inputs = [str(item) for item in data.get("refreshRuntimeInputs") or data.get("refreshInputs", [])]
        has_canonical = any(key in data for key in ["afterNoCommit", "afterCommit", "afterUnknown"])
        legacy_findings: list[dict[str, Any]] = []
        after_commit = data.get("afterCommit")
        if after_commit is None and not has_canonical and data.get("rerunRisk"):
            legacy_risk = str(data.get("rerunRisk"))
            if legacy_risk == "safe-with-new-inputs" and refresh_inputs:
                after_commit = "allowed-with-new-inputs"
            elif legacy_risk == "blocked":
                after_commit = "blocked"
            elif legacy_risk == "requires-confirmation":
                after_commit = "requires-confirmation"
            elif legacy_risk == "safe":
                after_commit = "allowed"
            else:
                legacy_findings.append(
                    {
                        "severity": "blocking",
                        "code": "rerun-policy-legacy-ambiguous",
                        "path": "rerunPolicy.rerunRisk",
                        "message": "Legacy rerunRisk cannot be migrated without an unambiguous canonical rerun policy.",
                    }
                )
        return cls(
            afterNoCommit=data.get("afterNoCommit", "allowed"),
            afterCommit=after_commit or "blocked",
            afterUnknown=data.get("afterUnknown", "requires-confirmation"),
            refreshRuntimeInputs=refresh_inputs,
            notes=data.get("notes"),
            legacyFindings=legacy_findings,
        )

    def validate(self, *, refreshable_inputs: list[str] | None = None) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        valid = {"allowed", "allowed-with-new-inputs", "requires-confirmation", "blocked"}
        for field_name in ["afterNoCommit", "afterCommit", "afterUnknown"]:
            value = getattr(self, field_name)
            if value not in valid:
                findings.append(
                    {
                        "severity": "blocking",
                        "code": "rerun-policy-invalid-decision",
                        "path": f"rerunPolicy.{field_name}",
                        "message": f"Unsupported rerun decision: {value}",
                    }
                )
        refreshable = set(refreshable_inputs or [])
        declared = set(self.refreshRuntimeInputs)
        findings.extend([dict(item) for item in self.legacyFindings])
        if self.afterCommit == "allowed-with-new-inputs" and not declared and not refreshable:
            findings.append(
                {
                    "severity": "blocking",
                    "code": "rerun-refresh-input-missing",
                    "path": "rerunPolicy.refreshRuntimeInputs",
                    "message": "Rerun after commit requires at least one declared refreshable generated runtime input.",
                }
            )
        if declared and refreshable and not declared <= refreshable:
            unsupported = ", ".join(sorted(declared - refreshable))
            findings.append(
                {
                    "severity": "blocking",
                    "code": "rerun-refresh-input-unsupported",
                    "path": "rerunPolicy.refreshRuntimeInputs",
                    "message": f"Rerun policy references inputs that are not refreshable: {unsupported}",
                }
            )
        return findings

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("legacyFindings", None)
        return _clean(data)


@dataclass(slots=True)
class ResourceIdentity:
    resourceType: str = ""
    identityStrategy: ResourceIdentityStrategy | str = "manual-confirmation"
    identityInput: str | None = None
    postCommitBinding: str | None = None
    postCommitBindings: list[str] = field(default_factory=list)
    collisionPolicy: CollisionPolicy | str = "requires-confirmation"
    targetScope: str | None = None
    confidence: ResourceIdentityConfidence | str = "unknown"
    present: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResourceIdentity":
        if not isinstance(data, dict) or not data:
            return cls(present=False)
        return cls(
            resourceType=str(data.get("resourceType", "")),
            identityStrategy=str(data.get("identityStrategy") or "manual-confirmation"),
            identityInput=data.get("identityInput"),
            postCommitBinding=data.get("postCommitBinding"),
            postCommitBindings=[str(item) for item in data.get("postCommitBindings", [])],
            collisionPolicy=str(data.get("collisionPolicy") or "requires-confirmation"),
            targetScope=data.get("targetScope"),
            confidence=str(data.get("confidence") or "unknown"),
            present=True,
        )

    def required_for(self, side_effect_class: str) -> bool:
        return side_effect_class in {"write", "external-notification"}

    def validate(self, *, side_effect_class: str, runtime_inputs: list[Any]) -> list[dict[str, Any]]:
        if not self.required_for(side_effect_class):
            return []
        if not self.present:
            return [
                {
                    "severity": "blocking",
                    "code": "resource-identity-missing",
                    "path": "resourceIdentity",
                    "message": "Write and external-notification use cases require explicit resourceIdentity.",
                }
            ]
        findings: list[dict[str, Any]] = []
        if not self.resourceType:
            findings.append(_identity_finding("resource-identity-type-missing", "resourceIdentity.resourceType", "Resource identity requires resourceType."))
        valid_strategies = {"generated-input", "provided-input", "post-commit-binding", "manual-confirmation"}
        if self.identityStrategy not in valid_strategies:
            findings.append(_identity_finding("resource-identity-strategy-invalid", "resourceIdentity.identityStrategy", f"Unsupported identityStrategy: {self.identityStrategy}"))
        runtime_by_name = {getattr(item, "name", ""): item for item in runtime_inputs}
        if self.identityStrategy == "generated-input":
            if not self.identityInput:
                findings.append(_identity_finding("resource-identity-input-missing", "resourceIdentity.identityInput", "generated-input identity requires identityInput."))
            else:
                runtime_input = runtime_by_name.get(self.identityInput)
                if runtime_input is None:
                    findings.append(_identity_finding("resource-identity-input-not-found", "resourceIdentity.identityInput", f"identityInput is not declared as a runtime input: {self.identityInput}"))
                elif getattr(runtime_input, "source", "") != "generated":
                    findings.append(_identity_finding("resource-identity-input-not-generated", "resourceIdentity.identityInput", f"identityInput must reference a generated runtime input: {self.identityInput}"))
                elif self.collisionPolicy == "avoid" and not bool(getattr(runtime_input, "refreshOnRerunAfterCommit", False)):
                    findings.append(_identity_finding("resource-identity-input-not-refreshable", "resourceIdentity.identityInput", f"collisionPolicy=avoid requires refreshable generated input: {self.identityInput}"))
        if self.collisionPolicy not in {"avoid", "allow-duplicates", "requires-confirmation"}:
            findings.append(_identity_finding("resource-identity-collision-policy-invalid", "resourceIdentity.collisionPolicy", f"Unsupported collisionPolicy: {self.collisionPolicy}"))
        return findings

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("present", None)
        return _clean(data) if self.present else {}


def _identity_finding(code: str, path: str, message: str) -> dict[str, Any]:
    return {"severity": "blocking", "code": code, "path": path, "message": message}


@dataclass(slots=True)
class GeneratedRuntimeInput:
    name: str
    purpose: str = ""
    generationStrategy: str = "template"
    seed: str | None = None
    template: str | None = None
    refreshOnRerunAfterCommit: bool = False
    persistValue: bool = False
    secretSafe: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeneratedRuntimeInput":
        generation = data.get("generation") if isinstance(data.get("generation"), dict) else {}
        return cls(
            name=str(data.get("name", "")),
            purpose=str(data.get("purpose", "")),
            generationStrategy=str(generation.get("strategy") or data.get("generationStrategy") or "template"),
            seed=generation.get("seed") or data.get("seed") or data.get("value"),
            template=generation.get("template") or data.get("template"),
            refreshOnRerunAfterCommit=bool(data.get("refreshOnRerunAfterCommit", False)),
            persistValue=bool(data.get("persistValue", False)),
            secretSafe=bool(data.get("secretSafe", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ResolvedRuntimeBinding:
    name: str
    value: str
    source: str = "generated"
    runId: str | None = None
    targetScope: str | None = None
    useCaseAlias: str | None = None
    refreshed: bool = False
    committed: bool = False
    status: ResolvedBindingStatus = "prepared"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResolvedRuntimeBinding":
        return cls(
            name=str(data.get("name", "")),
            value=str(data.get("value", "")),
            source=str(data.get("source", "generated")),
            runId=data.get("runId"),
            targetScope=data.get("targetScope"),
            useCaseAlias=data.get("useCaseAlias"),
            refreshed=bool(data.get("refreshed", False)),
            committed=bool(data.get("committed", False)),
            status=data.get("status") or ("committed" if data.get("committed") else "prepared"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class NamedOutput:
    name: str
    value: str
    sourceBinding: str
    publishedByRunId: str
    useCaseAlias: str
    targetScope: str | None = None
    resourceType: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NamedOutput":
        return cls(
            name=str(data.get("name", "")),
            value=str(data.get("value", "")),
            sourceBinding=str(data.get("sourceBinding") or data.get("source") or ""),
            publishedByRunId=str(data.get("publishedByRunId", "")),
            useCaseAlias=str(data.get("useCaseAlias", "")),
            targetScope=data.get("targetScope"),
            resourceType=data.get("resourceType"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ValidationFinding:
    code: str
    severity: str
    category: str
    message: str
    repairability: str = "not-repairable"
    suggestedReplacement: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class SideEffectDeclaration:
    sideEffectClass: SideEffectClass = "none"
    policyMode: SideEffectPolicyMode = "observe"
    commitStepId: str | None = None
    allowed: list[dict[str, Any]] = field(default_factory=list)
    forbidden: list[dict[str, Any]] = field(default_factory=list)
    confirmationSignals: list[dict[str, Any]] = field(default_factory=list)
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SideEffectDeclaration":
        data = data if isinstance(data, dict) else {}
        side_effect_class = str(data.get("class") or data.get("sideEffectClass") or "none")
        return cls(
            sideEffectClass=side_effect_class,  # type: ignore[arg-type]
            policyMode=data.get("mode") or data.get("policyMode") or _default_side_effect_mode(side_effect_class),
            commitStepId=data.get("commitStepId") or data.get("commitStep"),
            allowed=list(data.get("allowed", [])),
            forbidden=list(data.get("forbidden", [])),
            confirmationSignals=list(data.get("confirmationSignals", [])),
            notes=data.get("notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["class"] = data.pop("sideEffectClass")
        data["mode"] = data.pop("policyMode")
        return _clean(data)


def _default_side_effect_mode(side_effect_class: str) -> SideEffectPolicyMode:
    return "enforce" if side_effect_class in {"write", "external-notification"} else "observe"


@dataclass(slots=True)
class RuntimeOutputDeclaration:
    name: str
    source: str
    selector: str | None = None
    required: bool = False
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeOutputDeclaration":
        return cls(
            name=str(data.get("name", "")),
            source=str(data.get("source", "")),
            selector=data.get("selector"),
            required=bool(data.get("required", False)),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RuntimeOutputResult:
    name: str
    status: str
    value: str | None = None
    source: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeOutputResult":
        return cls(
            name=str(data.get("name", "")),
            status=str(data.get("status", "unknown")),
            value=data.get("value"),
            source=data.get("source"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ResolvedRuntimeInput:
    name: str
    value: str
    source: str = "generated"
    runId: str | None = None
    refreshed: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResolvedRuntimeInput":
        return cls(
            name=str(data.get("name", "")),
            value=str(data.get("value", "")),
            source=str(data.get("source", "generated")),
            runId=data.get("runId"),
            refreshed=bool(data.get("refreshed", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class PostCommitInterpretation:
    postCommit: bool = False
    sideEffectMayExist: bool = False
    executionStatus: str | None = None
    verificationStatus: str | None = None
    sideEffectStatus: str | None = None
    failurePhase: str | None = None
    rerunRisk: str | None = None
    message: str = ""

    @property
    def specMessage(self) -> str:
        return self.message

    @classmethod
    def from_core_result(cls, core_result: dict[str, Any] | None) -> "PostCommitInterpretation":
        data = core_result.get("data") if isinstance(core_result, dict) and isinstance(core_result.get("data"), dict) else core_result
        data = data if isinstance(data, dict) else {}
        report = data.get("report") if isinstance(data.get("report"), dict) else {}
        source = report or data
        side_effects = source.get("sideEffects") if isinstance(source.get("sideEffects"), dict) else {}
        classification = source.get("resultClassification") if isinstance(source.get("resultClassification"), dict) else {}
        commit_step = side_effects.get("commitStep") if isinstance(side_effects.get("commitStep"), dict) else {}
        commit_reached = bool(commit_step.get("reached"))
        failure_phase = str(classification.get("failurePhase") or side_effects.get("failurePhase") or "unknown")
        side_effect_status = str(classification.get("sideEffectStatus") or side_effects.get("status") or "unknown")
        post_commit = commit_reached and failure_phase in {"post-commit", "post-verification"}
        risky_statuses = {"possible", "likely-committed", "committed-confirmed", "violated", "unknown"}
        side_effect_may_exist = commit_reached and side_effect_status in risky_statuses
        if post_commit or side_effect_may_exist:
            message = "The commit step was reached; the side effect may already exist before final verification completed."
        else:
            message = "No committed side effect was identified from the public Core result."
        return cls(
            postCommit=post_commit,
            sideEffectMayExist=side_effect_may_exist,
            executionStatus=classification.get("executionStatus"),
            verificationStatus=classification.get("verificationStatus"),
            sideEffectStatus=side_effect_status,
            failurePhase=failure_phase,
            rerunRisk=classification.get("rerunRisk"),
            message=message,
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ConfirmationRequirement:
    id: str
    alias: str
    riskClass: str
    reason: str
    scope: str
    recommendedAction: str
    blocksExecution: bool = True
    expiresWhen: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfirmationRequirement":
        return cls(
            id=str(data.get("id", "")),
            alias=str(data.get("alias", "")),
            riskClass=str(data.get("riskClass", "")),
            reason=str(data.get("reason", "")),
            scope=str(data.get("scope", "")),
            recommendedAction=str(data.get("recommendedAction", "")),
            blocksExecution=bool(data.get("blocksExecution", True)),
            expiresWhen=[str(item) for item in data.get("expiresWhen", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class CredentialReadinessHint:
    credentialGroup: str
    expectedSource: str = "environment"
    requiredRuntimeNames: list[str] = field(default_factory=list)
    preparationHint: str = ""
    valuesIncluded: bool = False
    updatedAt: str | None = None
    schemaVersion: str = "verifysignal-spec-credential-readiness-hint/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CredentialReadinessHint":
        return cls(
            credentialGroup=str(data.get("credentialGroup") or data.get("group") or ""),
            expectedSource=str(data.get("expectedSource") or data.get("source") or "environment"),
            requiredRuntimeNames=[str(item) for item in data.get("requiredRuntimeNames", [])],
            preparationHint=str(data.get("preparationHint") or data.get("hint") or ""),
            valuesIncluded=bool(data.get("valuesIncluded", False)),
            updatedAt=data.get("updatedAt"),
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-credential-readiness-hint/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ReadinessSnapshot:
    alias: str
    status: ReadinessCurrentStatus
    checkedAt: str
    artifactFingerprints: dict[str, str] = field(default_factory=dict)
    specVersion: str | None = None
    artifactContractVersion: str | None = None
    coreVersion: str | None = None
    coreContractVersion: str | None = None
    targetProjectRevision: str | None = None
    testedCodeScopeStatus: Literal["known", "unknown"] = "unknown"
    environmentBoundCredentialGroups: list[str] = field(default_factory=list)
    sideEffectClass: SideEffectClass = "none"
    refreshImpactStatus: ImpactStatus | None = None
    invalidationReasons: list[dict[str, str]] = field(default_factory=list)
    summary: str | None = None
    schemaVersion: str = "verifysignal-spec-readiness-snapshot/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReadinessSnapshot":
        return cls(
            alias=str(data.get("alias", "")),
            status=data.get("status", "unknown"),
            checkedAt=str(data.get("checkedAt", "")),
            artifactFingerprints={str(k): str(v) for k, v in dict(data.get("artifactFingerprints", {})).items()},
            specVersion=data.get("specVersion"),
            artifactContractVersion=data.get("artifactContractVersion"),
            coreVersion=data.get("coreVersion"),
            coreContractVersion=data.get("coreContractVersion"),
            targetProjectRevision=data.get("targetProjectRevision"),
            testedCodeScopeStatus=data.get("testedCodeScopeStatus", "unknown"),
            environmentBoundCredentialGroups=[str(item) for item in data.get("environmentBoundCredentialGroups", [])],
            sideEffectClass=data.get("sideEffectClass", "none"),
            refreshImpactStatus=data.get("refreshImpactStatus"),
            invalidationReasons=list(data.get("invalidationReasons", [])),
            summary=data.get("summary"),
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-readiness-snapshot/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RefreshImpactResult:
    alias: str
    status: ImpactStatus
    reason: str = ""
    affectedAreas: list[str] = field(default_factory=list)
    recommendedAction: str = "none"
    generatedAt: str | None = None
    schemaVersion: str = "verifysignal-spec-refresh-impact/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RefreshImpactResult":
        return cls(
            alias=str(data.get("alias", "")),
            status=data.get("status", "unknown"),
            reason=str(data.get("reason", "")),
            affectedAreas=[str(item) for item in data.get("affectedAreas", [])],
            recommendedAction=str(data.get("recommendedAction", "none")),
            generatedAt=data.get("generatedAt"),
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-refresh-impact/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class UnderstandingFreshnessState:
    status: UnderstandingStatus = "unknown"
    ageDays: int | None = None
    commitsBehind: int | None = None
    workflowContext: str = "list"
    useCaseImpact: Literal["affected", "unaffected", "unknown", "not-applicable"] = "not-applicable"
    policy: UnderstandingPolicy = "allow"
    recommendedAction: str = "continue"
    reasons: list[str] = field(default_factory=list)
    schemaVersion: str = "verifysignal-spec-understanding-freshness-state/v1"

    @classmethod
    def from_context(
        cls,
        *,
        stale: bool,
        workflow_context: str,
        use_case_impact: str = "not-applicable",
        side_effect_class: str = "none",
        age_days: int | None = None,
        commits_behind: int | None = None,
        reasons: list[str] | None = None,
    ) -> "UnderstandingFreshnessState":
        if not stale:
            return cls(
                status="current",
                ageDays=age_days,
                commitsBehind=commits_behind,
                workflowContext=workflow_context,
                useCaseImpact=use_case_impact,  # type: ignore[arg-type]
                policy="allow",
                recommendedAction="continue",
                reasons=reasons or [],
            )
        inventory_contexts = {"understand", "discovery", "specify", "recommend", "recommend-first-run"}
        write_like = side_effect_class in {"write", "external-notification"}
        if workflow_context in inventory_contexts:
            policy, action = "block", "refresh-understanding"
        elif use_case_impact == "affected" and workflow_context == "run":
            policy, action = "block", "validate"
        elif use_case_impact == "unknown" and write_like and workflow_context == "run":
            policy, action = "requires-confirmation", "confirm"
        elif use_case_impact == "affected":
            policy, action = "warn", "validate"
        else:
            policy, action = "warn", "continue"
        return cls(
            status="stale",
            ageDays=age_days,
            commitsBehind=commits_behind,
            workflowContext=workflow_context,
            useCaseImpact=use_case_impact if use_case_impact in {"affected", "unaffected", "unknown"} else "not-applicable",  # type: ignore[arg-type]
            policy=policy,  # type: ignore[arg-type]
            recommendedAction=action,
            reasons=reasons or [],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnderstandingFreshnessState":
        return cls(
            status=data.get("status", "unknown"),
            ageDays=data.get("ageDays"),
            commitsBehind=data.get("commitsBehind"),
            workflowContext=str(data.get("workflowContext", "list")),
            useCaseImpact=data.get("useCaseImpact", "not-applicable"),
            policy=data.get("policy", "allow"),
            recommendedAction=str(data.get("recommendedAction", "continue")),
            reasons=[str(item) for item in data.get("reasons", [])],
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-understanding-freshness-state/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ArtifactCapabilityPolicy:
    capability: str
    appliesTo: list[str] = field(default_factory=list)
    severityWhenMissing: CapabilitySeverity = "warning"
    safetyCritical: bool = False
    migrationGuidance: str = ""
    schemaVersion: str = "verifysignal-spec-artifact-capability-policy/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactCapabilityPolicy":
        return cls(
            capability=str(data.get("capability", "")),
            appliesTo=[str(item) for item in data.get("appliesTo", [])],
            severityWhenMissing=data.get("severityWhenMissing", "warning"),
            safetyCritical=bool(data.get("safetyCritical", False)),
            migrationGuidance=str(data.get("migrationGuidance", "")),
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-artifact-capability-policy/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ArtifactCapabilityStamp:
    specVersion: str
    artifactContractVersion: str
    authoredAt: str
    capabilities: list[str] = field(default_factory=list)
    schemaVersion: str = "verifysignal-spec-artifact-capability-stamp/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactCapabilityStamp":
        return cls(
            specVersion=str(data.get("specVersion", "")),
            artifactContractVersion=str(data.get("artifactContractVersion", "")),
            authoredAt=str(data.get("authoredAt", "")),
            capabilities=[str(item) for item in data.get("capabilities", [])],
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-artifact-capability-stamp/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class SideEffectLifecycleDeclaration:
    cleanupPolicy: CleanupPolicy = "not-declared"
    cleanupRequired: bool = False
    trackingIntent: str = "none"
    instructions: str = ""
    schemaVersion: str = "verifysignal-spec-side-effect-lifecycle/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SideEffectLifecycleDeclaration":
        data = data if isinstance(data, dict) else {}
        return cls(
            cleanupPolicy=data.get("cleanupPolicy", "not-declared"),
            cleanupRequired=bool(data.get("cleanupRequired", False)),
            trackingIntent=str(data.get("trackingIntent", "none")),
            instructions=str(data.get("instructions", "")),
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-side-effect-lifecycle/v1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class ArtifactReference:
    path: str
    kind: Literal["run-request", "skill", "external"]
    generated: bool = True
    id: str | None = None
    version: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactReference":
        return cls(
            path=str(data.get("path", "")),
            kind=data.get("kind", "external"),
            generated=bool(data.get("generated", False)),
            id=data.get("id"),
            version=data.get("version"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RuntimeInputRequirement:
    name: str
    kind: Literal["parameter", "credential", "precondition-input"] = "parameter"
    required: bool = True
    description: str = ""
    source: Literal["prompt", "environment", "local-config", "default", "generated", "named-output"] = "prompt"
    envVar: str | None = None
    credentialGroup: str | None = None
    persistValue: bool = False
    template: str | None = None
    default: str | None = None
    value: str | None = None
    refreshOnRerunAfterCommit: bool = False
    references: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeInputRequirement":
        return cls(
            name=str(data.get("name", "")),
            kind=data.get("kind", "parameter"),
            required=bool(data.get("required", True)),
            description=str(data.get("description", "")),
            source=data.get("source", "prompt"),
            envVar=data.get("envVar"),
            credentialGroup=data.get("credentialGroup"),
            persistValue=bool(data.get("persistValue", False)),
            template=data.get("template"),
            default=data.get("default"),
            value=data.get("value"),
            refreshOnRerunAfterCommit=bool(data.get("refreshOnRerunAfterCommit", False)),
            references=[str(item) for item in data.get("references", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RunProfile:
    name: str = "normal"
    description: str = ""
    headed: bool = False
    slowMoMs: int = 0
    outputDir: str | None = None
    assumePreconditionsReady: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunProfile":
        return cls(
            name=str(data.get("name", "normal")),
            description=str(data.get("description", "")),
            headed=bool(data.get("headed", False)),
            slowMoMs=int(data.get("slowMoMs", 0) or 0),
            outputDir=data.get("outputDir"),
            assumePreconditionsReady=bool(data.get("assumePreconditionsReady", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class AuthoringQuestion:
    id: str
    prompt: str
    reason: str = ""
    status: Literal["pending", "answered", "deferred"] = "pending"
    answerSummary: str | None = None
    affects: str | None = None
    suggestedAnswer: dict[str, Any] | None = None
    suggestionSource: str | None = None
    requiresConfirmation: bool = False
    confirmationSource: Literal["direct-user", "explicit-command"] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthoringQuestion":
        return cls(
            id=str(data.get("id", "")),
            prompt=str(data.get("prompt", "")),
            reason=str(data.get("reason", "")),
            status=data.get("status", "pending"),
            answerSummary=data.get("answerSummary"),
            affects=data.get("affects"),
            suggestedAnswer=(
                dict(data["suggestedAnswer"])
                if isinstance(data.get("suggestedAnswer"), dict)
                else None
            ),
            suggestionSource=data.get("suggestionSource"),
            requiresConfirmation=bool(data.get("requiresConfirmation", False)),
            confirmationSource=data.get("confirmationSource"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RunHistoryEntry:
    runId: str
    useCaseAlias: str
    profile: str
    status: str
    startedAt: str
    completedAt: str | None = None
    coreStatus: str | None = None
    coverageStatus: str | None = None
    profileSettings: dict[str, Any] | None = None
    selectedMainSkill: dict[str, Any] | str | None = None
    executedSkill: dict[str, Any] | str | None = None
    skillSelectionStatus: str | None = None
    gateCoverage: list[dict[str, Any]] = field(default_factory=list)
    missingRequiredGates: list[str] = field(default_factory=list)
    partialCoverage: list[dict[str, Any]] = field(default_factory=list)
    runtimeContradictions: list[dict[str, Any]] = field(default_factory=list)
    repairRecommendations: list[dict[str, Any]] = field(default_factory=list)
    sideEffectPolicy: dict[str, Any] | None = None
    sideEffects: dict[str, Any] | None = None
    runtimeOutputs: list[dict[str, Any]] = field(default_factory=list)
    resolvedRuntimeInputs: list[dict[str, Any]] = field(default_factory=list)
    postCommitInterpretation: dict[str, Any] | None = None
    rerunDecision: dict[str, Any] | None = None
    sideEffectLifecycle: dict[str, Any] | None = None
    summary: str | dict[str, Any] | None = None
    reportPath: str | None = None
    evidenceDir: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunHistoryEntry":
        return cls(
            runId=str(data.get("runId", "")),
            useCaseAlias=str(data.get("useCaseAlias", "")),
            profile=str(data.get("profile", "normal")),
            status=data.get("status", "error"),
            startedAt=str(data.get("startedAt", "")),
            completedAt=data.get("completedAt"),
            coreStatus=data.get("coreStatus"),
            coverageStatus=data.get("coverageStatus"),
            profileSettings=data.get("profileSettings"),
            selectedMainSkill=data.get("selectedMainSkill"),
            executedSkill=data.get("executedSkill"),
            skillSelectionStatus=data.get("skillSelectionStatus"),
            gateCoverage=list(data.get("gateCoverage", [])),
            missingRequiredGates=[str(item) for item in data.get("missingRequiredGates", [])],
            partialCoverage=list(data.get("partialCoverage", [])),
            runtimeContradictions=list(data.get("runtimeContradictions", [])),
            repairRecommendations=list(data.get("repairRecommendations", [])),
            sideEffectPolicy=data.get("sideEffectPolicy"),
            sideEffects=data.get("sideEffects"),
            runtimeOutputs=list(data.get("runtimeOutputs", [])),
            resolvedRuntimeInputs=list(data.get("resolvedRuntimeInputs", [])),
            postCommitInterpretation=data.get("postCommitInterpretation"),
            rerunDecision=data.get("rerunDecision"),
            sideEffectLifecycle=data.get("sideEffectLifecycle"),
            summary=data.get("summary"),
            reportPath=data.get("reportPath"),
            evidenceDir=data.get("evidenceDir"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class RepairSession:
    repairId: str
    useCaseAlias: str
    source: Literal["authoring-validation", "report-inspection"]
    findings: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    repairConfirmations: list[dict[str, Any]] = field(default_factory=list)
    applications: list[dict[str, Any]] = field(default_factory=list)
    repairFeedback: list[dict[str, Any]] = field(default_factory=list)
    stageCards: list[dict[str, Any]] = field(default_factory=list)
    approvalStatus: Literal[
        "pending", "proposed", "approved", "rejected", "conflict", "applied", "revalidation-failed", "revalidation-unavailable"
    ] = "pending"
    appliedAt: str | None = None
    revalidation: dict[str, Any] | None = None
    readyForRun: bool = False
    nextAction: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepairSession":
        return cls(
            repairId=str(data.get("repairId", "")),
            useCaseAlias=str(data.get("useCaseAlias", "")),
            source=data.get("source", "authoring-validation"),
            findings=list(data.get("findings", [])),
            proposals=list(data.get("proposals", [])),
            recommendations=list(data.get("recommendations", [])),
            repairConfirmations=list(data.get("repairConfirmations", [])),
            applications=list(data.get("applications", [])),
            repairFeedback=list(data.get("repairFeedback", [])),
            stageCards=list(data.get("stageCards", [])),
            approvalStatus=data.get("approvalStatus", "pending"),
            appliedAt=data.get("appliedAt"),
            revalidation=data.get("revalidation"),
            readyForRun=bool(data.get("readyForRun", False)),
            nextAction=data.get("nextAction"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class UseCaseRecord:
    alias: str
    title: str
    description: str
    targetSurface: str = "browser"
    status: Status = "draft"
    runRequest: ArtifactReference | None = None
    mainSkill: ArtifactReference | None = None
    skills: list[ArtifactReference] = field(default_factory=list)
    sourceOnlySkills: list[ArtifactReference] = field(default_factory=list)
    skillComposition: dict[str, Any] | None = None
    runtimeInputs: list[RuntimeInputRequirement] = field(default_factory=list)
    credentialRefs: dict[str, Any] = field(default_factory=dict)
    sessionRef: dict[str, Any] | None = None
    credentialGroups: list[dict[str, Any] | str] = field(default_factory=list)
    sideEffects: dict[str, Any] | None = None
    sideEffectLifecycle: dict[str, Any] | None = None
    resourceIdentity: dict[str, Any] | None = None
    runtimeOutputs: list[dict[str, Any]] = field(default_factory=list)
    resolvedRuntimeInputs: list[dict[str, Any]] = field(default_factory=list)
    rerunPolicy: dict[str, Any] | None = None
    writeFlowSummary: dict[str, Any] | None = None
    artifactCapabilities: dict[str, Any] | None = None
    profiles: list[RunProfile] = field(
        default_factory=lambda: [
            RunProfile(),
            RunProfile(name="debug", description="Visible browser debug profile", headed=True, slowMoMs=900),
            RunProfile(name="browser", description="Visible browser profile", headed=True, slowMoMs=900),
        ]
    )
    authoringQuestions: list[AuthoringQuestion] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=lambda: {"status": "unknown"})
    lastRun: dict[str, Any] | None = None
    repair: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    schemaVersion: str = "verifysignal-spec-use-case/v1"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UseCaseRecord":
        return cls(
            schemaVersion=str(data.get("schemaVersion", "verifysignal-spec-use-case/v1")),
            alias=str(data.get("alias", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            targetSurface=str(data.get("targetSurface", "browser")),
            status=data.get("status", "draft"),
            runRequest=ArtifactReference.from_dict(data["runRequest"]) if data.get("runRequest") else None,
            mainSkill=ArtifactReference.from_dict(data["mainSkill"]) if data.get("mainSkill") else None,
            skills=[ArtifactReference.from_dict(item) for item in data.get("skills", [])],
            sourceOnlySkills=[ArtifactReference.from_dict(item) for item in data.get("sourceOnlySkills", [])],
            skillComposition=data.get("skillComposition") if isinstance(data.get("skillComposition"), dict) else None,
            runtimeInputs=[RuntimeInputRequirement.from_dict(item) for item in data.get("runtimeInputs", [])],
            credentialRefs=dict(data.get("credentialRefs", {})),
            sessionRef=dict(data["sessionRef"]) if isinstance(data.get("sessionRef"), dict) else None,
            credentialGroups=list(data.get("credentialGroups", [])),
            sideEffects=data.get("sideEffects") if isinstance(data.get("sideEffects"), dict) else None,
            sideEffectLifecycle=data.get("sideEffectLifecycle") if isinstance(data.get("sideEffectLifecycle"), dict) else None,
            resourceIdentity=data.get("resourceIdentity") if isinstance(data.get("resourceIdentity"), dict) else None,
            runtimeOutputs=list(data.get("runtimeOutputs", [])),
            resolvedRuntimeInputs=list(data.get("resolvedRuntimeInputs", [])),
            rerunPolicy=data.get("rerunPolicy") if isinstance(data.get("rerunPolicy"), dict) else None,
            writeFlowSummary=data.get("writeFlowSummary") if isinstance(data.get("writeFlowSummary"), dict) else None,
            artifactCapabilities=data.get("artifactCapabilities") if isinstance(data.get("artifactCapabilities"), dict) else None,
            profiles=[RunProfile.from_dict(item) for item in data.get("profiles", [])] or [RunProfile()],
            authoringQuestions=[AuthoringQuestion.from_dict(item) for item in data.get("authoringQuestions", [])],
            validation=dict(data.get("validation", {"status": "unknown"})),
            lastRun=data.get("lastRun"),
            repair=data.get("repair"),
            workflow=data.get("workflow"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["runRequest"] = self.runRequest.to_dict() if self.runRequest else None
        data["mainSkill"] = self.mainSkill.to_dict() if self.mainSkill else None
        data["skills"] = [item.to_dict() for item in self.skills]
        data["sourceOnlySkills"] = [item.to_dict() for item in self.sourceOnlySkills]
        data["runtimeInputs"] = [item.to_dict() for item in self.runtimeInputs]
        data["credentialRefs"] = dict(self.credentialRefs)
        data["sessionRef"] = dict(self.sessionRef) if self.sessionRef else None
        data["sideEffectLifecycle"] = dict(self.sideEffectLifecycle) if self.sideEffectLifecycle else None
        data["resourceIdentity"] = dict(self.resourceIdentity) if self.resourceIdentity else None
        data["runtimeOutputs"] = list(self.runtimeOutputs)
        data["resolvedRuntimeInputs"] = list(self.resolvedRuntimeInputs)
        data["artifactCapabilities"] = dict(self.artifactCapabilities) if self.artifactCapabilities else None
        data["profiles"] = [item.to_dict() for item in self.profiles]
        data["authoringQuestions"] = [item.to_dict() for item in self.authoringQuestions]
        return _clean(data)


@dataclass(slots=True)
class ManagedFileRecord:
    path: str
    sha256: str
    source: str
    kind: Literal["agent-skill", "context", "workspace-template", "manifest", "onboarding-guide"]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManagedFileRecord":
        return cls(path=str(data.get("path", "")), sha256=str(data.get("sha256", "")), source=str(data.get("source", "")), kind=data.get("kind", "agent-skill"))

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(slots=True)
class AgentIntegrationState:
    key: str
    displayName: str
    installedAt: str
    default: bool = False
    managedFiles: list[ManagedFileRecord] = field(default_factory=list)
    invokeStyle: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentIntegrationState":
        return cls(
            key=str(data.get("key", "")),
            displayName=str(data.get("displayName", "")),
            installedAt=str(data.get("installedAt", "")),
            default=bool(data.get("default", False)),
            managedFiles=[ManagedFileRecord.from_dict(item) for item in data.get("managedFiles", [])],
            invokeStyle=str(data.get("invokeStyle", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["managedFiles"] = [item.to_dict() for item in self.managedFiles]
        return _clean(data)
