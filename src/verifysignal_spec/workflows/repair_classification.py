from __future__ import annotations

from typing import Any

from .models import RuntimeFeedbackFinding


def classify_runtime_feedback(finding: dict[str, Any], *, source: str = "report-inspection") -> RuntimeFeedbackFinding:
    code = str(finding.get("code") or "")
    message = str(finding.get("message") or finding.get("reason") or "")
    text = f"{code} {message}".lower()
    gate_id = str(finding.get("gateId") or finding.get("path") or "").strip()
    evidence = [item for item in [code, message] if item]

    if (
        code.startswith("side-effect-")
        and any(term in code for term in ["violation", "observation-review", "policy-changed"])
    ) or any(
        term in text
        for term in [
            "side-effect policy violation",
            "side effect policy violation",
            "side effect was observed",
            "side-effect observation review",
        ]
    ):
        return RuntimeFeedbackFinding(
            id=_id("side-effect-policy", code),
            source=source,  # type: ignore[arg-type]
            category="side-effect-policy-issue",
            severity="blocked",
            summary=message or "Observed network activity requires an explicit side-effect policy review.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="blocked",
            confidence="high",
        )
    if code.startswith("entitlement.") or code in {"api.unavailable", "distribution.unauthorized", "distribution.unavailable", "core.incompatible"}:
        return RuntimeFeedbackFinding(
            id=_id("runtime-entitlement", code),
            source=source,  # type: ignore[arg-type]
            category="environment-recovery",
            severity="blocked",
            summary=message or "VerifySignal runtime entitlement must be resolved before artifact repair.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="environment-recovery",
            confidence="high",
        )
    if any(term in text for term in ["unreachable", "redirected unexpectedly", "environment blocked", "target blocked"]):
        return RuntimeFeedbackFinding(
            id=_id("environment", code),
            source=source,  # type: ignore[arg-type]
            category="environment-recovery",
            severity="blocked",
            summary=message or "Target environment requires recovery before repair.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="environment-recovery",
            confidence="high",
        )
    if any(term in text for term in ["missing prerequisite", "missing baseurl", "missing credential", "unresolved placeholder"]):
        return RuntimeFeedbackFinding(
            id=_id("missing-prerequisite", code),
            source=source,  # type: ignore[arg-type]
            category="missing-prerequisite",
            severity="blocked",
            summary=message or "A runtime prerequisite is missing.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="blocked",
            confidence="high",
        )
    if code.startswith("skill-execution.") or any(term in text for term in ["helper-skill", "helper skill", "source-only", "execution-boundary", "executable skill boundary"]):
        return RuntimeFeedbackFinding(
            id=_id("skill-execution-boundary", code),
            source=source,  # type: ignore[arg-type]
            category="execution-boundary-issue",
            severity="blocked",
            summary=message or "Executable skill boundary must be repaired before weakening gates.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="implement-repair",
            confidence="high",
        )
    if any(term in text for term in ["strict-mode", "strict mode", "multiple elements", "locator matched", "resolved to", "selector did not match", "did not match"]):
        return RuntimeFeedbackFinding(
            id=_id("selector", code),
            source=source,  # type: ignore[arg-type]
            category="selector-issue",
            severity="failed",
            summary=message or "Selector did not identify the intended rendered result.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="implement-repair",
            confidence="high",
        )
    if any(term in text for term in ["wait-timeout", "timeout", "timed out", "skeleton", "still loading", "wait strategy", "client-side graphql", "ssr"]):
        return RuntimeFeedbackFinding(
            id=_id("wait-flow", code),
            source=source,  # type: ignore[arg-type]
            category="wait-flow-issue",
            severity="failed",
            summary=message or "Browser flow advanced before the rendered state was ready.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="implement-repair",
            confidence="high",
        )
    if any(term in text for term in ["empty state", "no results", "not seeded", "product state", "target data"]):
        return RuntimeFeedbackFinding(
            id=_id("data-product-state", code),
            source=source,  # type: ignore[arg-type]
            category="data-product-state-issue",
            severity="warning",
            summary=message or "Target data or product state differs from the planned validation intent.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="clarify",
            confidence="medium",
        )
    if any(term in text for term in ["missing gate", "missing-gate", "gateid", "gate id", "gate mapping", "mapped evidence", "no mapped evidence"]):
        return RuntimeFeedbackFinding(
            id=_id("coverage-mapping", code),
            source=source,  # type: ignore[arg-type]
            category="coverage-mapping-issue",
            severity="warning",
            summary=message or "Coverage mapping is incomplete or diagnostic.",
            evidence=evidence,
            affectedGates=[gate_id] if gate_id else [],
            recommendedAction="implement-repair",
            confidence="medium",
        )
    return RuntimeFeedbackFinding(
        id=_id("unsupported", code),
        source=source,  # type: ignore[arg-type]
        category="unsupported-feedback",
        severity="warning",
        summary=message or "Runtime feedback is not supported by the repair classifier.",
        evidence=evidence,
        affectedGates=[gate_id] if gate_id else [],
        recommendedAction="blocked",
        confidence="low",
    )


def _id(prefix: str, code: str) -> str:
    suffix = code.replace("_", "-").replace(" ", "-").strip("-") or "feedback"
    return f"{prefix}.{suffix}"
