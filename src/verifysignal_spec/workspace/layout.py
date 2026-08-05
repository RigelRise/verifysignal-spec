from __future__ import annotations

import re
from pathlib import Path

WORKSPACE_DIR = ".verifysignal"
WORKSPACE_FILE = "workspace.yaml"
PRODUCT_CONTEXT_FILE = "product-context.yaml"
REGISTRY_FILE = "registry.yaml"
USE_CASES_DIR = "use-cases"
RUN_REQUESTS_DIR = "run-requests"
SKILLS_DIR = "skills"
RUNS_DIR = "runs"
REPAIRS_DIR = "repairs"
INTEGRATIONS_DIR = "integrations"
MANIFESTS_DIR = "manifests"
WORKFLOWS_DIR = "workflows"
READINESS_DIR = "readiness"
CREDENTIAL_HINTS_DIR = "credential-hints"
CONFIRMATIONS_DIR = "confirmations"
REFRESH_IMPACT_DIR = "refresh-impact"
CAPABILITY_POLICIES_DIR = "capability-policies"
SUPERSEDE_REVIEWS_DIR = "supersede-reviews"
WORKFLOW_DEFINITIONS_DIR = "definitions"
WORKFLOW_RUNS_DIR = "runs"
WORKFLOW_USE_CASES_DIR = "use-cases"
WORKFLOW_GLOBAL_UNDERSTANDING = "understanding.md"

ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,199}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def resolve_project_path(project_path: str | None = None, here: bool = False) -> Path:
    if project_path and here:
        raise ValueError("Use either project path or --here, not both.")
    return Path(project_path or ".").resolve()


def workspace_root(project: Path) -> Path:
    return project / WORKSPACE_DIR


def registry_path(project: Path) -> Path:
    return workspace_root(project) / REGISTRY_FILE


def product_context_path(project: Path) -> Path:
    return workspace_root(project) / PRODUCT_CONTEXT_FILE


def use_case_path(project: Path, alias: str) -> Path:
    return workspace_root(project) / USE_CASES_DIR / f"{alias}.yaml"


def run_request_path(project: Path, alias: str) -> Path:
    return workspace_root(project) / RUN_REQUESTS_DIR / f"{alias}.yaml"


def skill_path(project: Path, name: str) -> Path:
    return workspace_root(project) / SKILLS_DIR / f"{name}.browser.md"


def canonical_run_request_path(project: Path, alias: str) -> Path:
    return run_request_path(project, ensure_path_safe_alias(alias))


def canonical_skill_path(project: Path, name: str) -> Path:
    return skill_path(project, ensure_path_safe_alias(name))


def canonical_run_request_rel(alias: str) -> str:
    return f"{WORKSPACE_DIR}/{RUN_REQUESTS_DIR}/{ensure_path_safe_alias(alias)}.yaml"


def canonical_skill_rel(name: str) -> str:
    return f"{WORKSPACE_DIR}/{SKILLS_DIR}/{ensure_path_safe_alias(name)}.browser.md"


def repair_path(project: Path, repair_id: str) -> Path:
    return workspace_root(project) / REPAIRS_DIR / f"{repair_id}.yaml"


def supersede_reviews_dir(project: Path, alias: str) -> Path:
    return workspace_root(project) / SUPERSEDE_REVIEWS_DIR / ensure_path_safe_alias(alias)


def supersede_review_path(project: Path, alias: str, review_id: str) -> Path:
    return supersede_reviews_dir(project, alias) / f"{ensure_path_safe_id(review_id)}.yaml"


def run_history_path(project: Path, alias: str, run_id: str) -> Path:
    return (
        workspace_root(project)
        / RUNS_DIR
        / ensure_path_safe_alias(alias)
        / f"{ensure_path_safe_run_id(run_id)}.yaml"
    )


def readiness_snapshot_path(project: Path, alias: str) -> Path:
    return workspace_root(project) / READINESS_DIR / f"{ensure_path_safe_alias(alias)}.yaml"


def credential_hint_path(project: Path, group: str) -> Path:
    return workspace_root(project) / CREDENTIAL_HINTS_DIR / f"{ensure_path_safe_alias(group)}.yaml"


def confirmation_requirement_path(project: Path, alias: str) -> Path:
    return workspace_root(project) / CONFIRMATIONS_DIR / f"{ensure_path_safe_alias(alias)}.yaml"


def refresh_impact_path(project: Path, alias: str) -> Path:
    return workspace_root(project) / REFRESH_IMPACT_DIR / f"{ensure_path_safe_alias(alias)}.yaml"


def capability_policy_path(project: Path, capability: str) -> Path:
    return workspace_root(project) / CAPABILITY_POLICIES_DIR / f"{ensure_path_safe_alias(capability)}.yaml"


def integration_state_path(project: Path) -> Path:
    return workspace_root(project) / INTEGRATIONS_DIR / "state.yaml"


def manifest_path(project: Path, integration_key: str) -> Path:
    return workspace_root(project) / INTEGRATIONS_DIR / MANIFESTS_DIR / f"{integration_key}.yaml"


def workflows_root(project: Path) -> Path:
    return workspace_root(project) / WORKFLOWS_DIR


def workflow_definitions_dir(project: Path) -> Path:
    return workflows_root(project) / WORKFLOW_DEFINITIONS_DIR


def workflow_definition_path(project: Path, workflow_id: str) -> Path:
    return workflow_definitions_dir(project) / f"{workflow_id}.yaml"


def workflow_runs_dir(project: Path) -> Path:
    return workflows_root(project) / WORKFLOW_RUNS_DIR


def workflow_run_path(project: Path, run_id: str) -> Path:
    return workflow_runs_dir(project) / f"{run_id}.yaml"


def workflow_use_cases_dir(project: Path) -> Path:
    return workflows_root(project) / WORKFLOW_USE_CASES_DIR


def workflow_use_case_dir(project: Path, alias: str) -> Path:
    return workflow_use_cases_dir(project) / ensure_path_safe_alias(alias)


def workflow_state_path(project: Path, alias: str) -> Path:
    return workflow_use_case_dir(project, alias) / "state.yaml"


def workflow_stage_document_path(project: Path, alias: str, stage: str) -> Path:
    filename = {
        "understand": "understanding.md",
        "specify": "spec.md",
        "clarify": "clarifications.md",
        "plan": "plan.md",
        "tasks": "tasks.md",
        "implement": "handoff.md",
        "validate": "validation.md",
        "run": "validation.md",
        "repair": "repair.md",
    }.get(stage, f"{stage}.md")
    return workflow_use_case_dir(project, alias) / filename


def canonical_workflow_stage_document_rel(project: Path, alias: str, stage: str) -> str:
    return to_project_relative(project, workflow_stage_document_path(project, alias, stage))


def workflow_global_understanding_path(project: Path) -> Path:
    return workflows_root(project) / WORKFLOW_GLOBAL_UNDERSTANDING


def ensure_path_safe_alias(alias: str) -> str:
    if not ALIAS_RE.match(alias):
        raise ValueError("Alias must be lowercase path-safe text using letters, numbers, '.', '_' or '-' and at most 80 characters.")
    return alias


def ensure_path_safe_id(value: str) -> str:
    # For SYSTEM-GENERATED ids/filenames (e.g. supersede review ids) that are charset-safe but
    # may legitimately exceed the 80-char alias bound. NOT for user-facing aliases.
    if not ID_RE.match(value):
        raise ValueError("Generated id must be lowercase path-safe text (letters, numbers, '.', '_', '-'), up to 200 characters.")
    return value


def ensure_path_safe_run_id(value: str) -> str:
    if not isinstance(value, str) or not RUN_ID_RE.fullmatch(value):
        raise ValueError(
            "Run id must be path-safe text using letters, numbers, '.', '_' or '-' and at most 200 characters."
        )
    return value


def to_project_relative(project: Path, path: Path) -> str:
    return path.resolve().relative_to(project.resolve()).as_posix()


def is_canonical_generated_skill_path(path: str) -> bool:
    prefix = f"{WORKSPACE_DIR}/{SKILLS_DIR}/"
    if not path.startswith(prefix) or not path.endswith(".browser.md"):
        return False
    return "/" not in path.removeprefix(prefix)


def project_relative_path(project: Path, rel_path: str) -> Path:
    path = (project / rel_path).resolve()
    project_root = project.resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Path escapes target project: {rel_path}") from exc
    return path


def workspace_dirs(project: Path) -> list[Path]:
    root = workspace_root(project)
    return [
        root,
        root / USE_CASES_DIR,
        root / RUN_REQUESTS_DIR,
        root / SKILLS_DIR,
        root / RUNS_DIR,
        root / REPAIRS_DIR,
        root / READINESS_DIR,
        root / CREDENTIAL_HINTS_DIR,
        root / CONFIRMATIONS_DIR,
        root / REFRESH_IMPACT_DIR,
        root / CAPABILITY_POLICIES_DIR,
        root / SUPERSEDE_REVIEWS_DIR,
        root / INTEGRATIONS_DIR,
        root / INTEGRATIONS_DIR / MANIFESTS_DIR,
        root / WORKFLOWS_DIR,
        root / WORKFLOWS_DIR / WORKFLOW_DEFINITIONS_DIR,
        root / WORKFLOWS_DIR / WORKFLOW_RUNS_DIR,
        root / WORKFLOWS_DIR / WORKFLOW_USE_CASES_DIR,
    ]
