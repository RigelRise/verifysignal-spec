from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .commands import author as author_command
from .commands import check as check_command
from .commands import core_setup as core_setup_command
from .commands import crystallize as crystallize_command
from .commands import discover as discover_command
from .commands import init as init_command
from .commands import integration as integration_command
from .commands import list as list_command
from .commands import probe as probe_command
from .commands import repair as repair_command
from .commands import run as run_command
from .commands import validate as validate_command
from .commands import workflow as workflow_command
from .core.errors import CoreIncompatibleError, CoreMissingError, RuntimeInputError
from .workspace.layout import resolve_project_path

EXIT_SUCCESS = 0
EXIT_VALIDATION_FAILED = 2
EXIT_CORE_FAILED = 3
EXIT_APPROVAL_REQUIRED = 4
EXIT_INPUT_MISSING = 5


def create_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog or _program_name(), description="VerifySignal CLI")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a target repository")
    init_parser.add_argument("project_path", nargs="?")
    init_parser.add_argument("--here", action="store_true")
    init_parser.add_argument("--integration", choices=["codex", "claude"], required=True)
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument("--core-cmd", help="VerifySignal Core executable, command string, or local Core repository path")
    init_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    init_parser.add_argument("--json", action="store_true")

    check_parser = subparsers.add_parser("check", help="Check workspace and Core readiness")
    check_parser.add_argument("--project", default=".")
    check_parser.add_argument("--core-cmd", help="VerifySignal Core executable, command string, or local Core repository path")
    check_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    check_parser.add_argument("--json", action="store_true")

    author_parser = subparsers.add_parser("author", help="Author a browser use case")
    author_parser.add_argument("alias")
    author_parser.add_argument("description")
    author_parser.add_argument("--project", default=".")
    author_parser.add_argument("--run-request")
    author_parser.add_argument("--skill", action="append", default=[])
    author_parser.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", help="List use cases")
    list_parser.add_argument("--project", default=".")
    list_parser.add_argument("--json", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="Validate a use case")
    validate_parser.add_argument("alias")
    validate_parser.add_argument("--project", default=".")
    validate_parser.add_argument("--runtime-readiness", action="store_true")
    validate_parser.add_argument("--core-cmd", help="Override configured VerifySignal Core command")
    validate_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    validate_parser.add_argument("--json", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run a use case")
    run_parser.add_argument("alias")
    run_parser.add_argument("--project", default=".")
    run_parser.add_argument("--profile", default="normal")
    run_parser.add_argument("--slow-mo", dest="slow_mo", type=int, help="Override browser slow motion in milliseconds for this run")
    run_parser.add_argument("--record", action="store_true", help="Record this run's network activity so it can be crystallized into a fixture")
    run_parser.add_argument("--replay", help="Replay this run against a crystallized fixture instead of the live target")
    run_parser.add_argument("--core-cmd", help="Override configured VerifySignal Core command")
    run_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    run_parser.add_argument("--json", action="store_true")
    run_parser.add_argument("--non-interactive", action="store_true")
    run_parser.add_argument("--confirm-risk", action="append", default=[], help="Confirm a structured risky-run confirmation id from workflow check run")

    repair_parser = subparsers.add_parser("repair", help="Repair a use case")
    repair_parser.add_argument("alias")
    repair_parser.add_argument("--project", default=".")
    repair_parser.add_argument("--from-report")
    repair_parser.add_argument("--approve", action="store_true")
    repair_parser.add_argument("--core-cmd", help="Override configured VerifySignal Core command")
    repair_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    repair_parser.add_argument("--json", action="store_true")

    discover_parser = subparsers.add_parser("discover", help="Ground a drafted browser skill's targets against the live DOM via Core")
    discover_parser.add_argument("--url", required=True, help="Page URL to ground targets against")
    discover_parser.add_argument("--skill", required=True, help="Drafted browser skill Markdown path")
    discover_parser.add_argument("--project", default=".")
    discover_parser.add_argument("--core-cmd", help="Override configured VerifySignal Core command")
    discover_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    discover_parser.add_argument("--json", action="store_true")

    probe_parser = subparsers.add_parser("probe", help="Exercise a browser run request through its pre-commit boundary via Core")
    probe_parser.add_argument("run_request", help="Run request path")
    probe_parser.add_argument("--skill", action="append", required=True, help="Browser skill path; repeat to preserve execution order")
    probe_parser.add_argument("--project", default=".")
    probe_parser.add_argument("--headed", action="store_true")
    probe_parser.add_argument("--slow-mo", dest="slow_mo", type=int, default=0, help="Browser slow motion in milliseconds")
    probe_parser.add_argument("--core-cmd", help="Override configured VerifySignal Core command")
    probe_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    probe_parser.add_argument("--json", action="store_true")

    crystallize_parser = subparsers.add_parser("crystallize", help="Crystallize a completed run into a reusable fixture via Core")
    crystallize_parser.add_argument("run_dir", help="Completed run directory to crystallize")
    crystallize_parser.add_argument("--out", help="Fixture output directory")
    crystallize_parser.add_argument("--project", default=".")
    crystallize_parser.add_argument("--core-cmd", help="Override configured VerifySignal Core command")
    crystallize_parser.add_argument("--api-base-url", help="Override the VerifySignal entitlement API base URL for staging, local development, or tests")
    crystallize_parser.add_argument("--json", action="store_true")

    core_parser = subparsers.add_parser("core", help="Inspect configured VerifySignal Core")
    core_sub = core_parser.add_subparsers(dest="core_command", required=True)
    core_version = core_sub.add_parser("version")
    core_version.add_argument("--project", default=".")
    core_version.add_argument("--core-cmd", help="VerifySignal Core executable, command string, or local Core repository path")
    core_version.add_argument("--json", action="store_true")
    core_setup = core_sub.add_parser(
        "setup",
        help="Discover, verify, and persist an existing VerifySignal Core command",
        description="Discover, verify, and persist an existing VerifySignal Core command",
    )
    core_setup.add_argument("--project", default=".")
    core_setup.add_argument("--core-cmd", help="VerifySignal Core executable, command string, or local Core repository path")
    core_setup.add_argument("--no-persist", action="store_true", help="Use an explicit Core command for this setup invocation without saving it")
    core_setup.add_argument("--json", action="store_true")

    policy_parser = subparsers.add_parser("policy", help="Manage a use case side-effect policy")
    policy_sub = policy_parser.add_subparsers(dest="policy_command", required=True)
    policy_set = policy_sub.add_parser("set", help="Set a use case's side-effect policy class without re-persisting implement")
    policy_set.add_argument("alias")
    policy_set.add_argument("--class", dest="policy_class", required=True, choices=["none", "authenticated-read", "write", "external-notification"])
    policy_set.add_argument("--mode", choices=["enforce", "warn", "observe"])
    policy_set.add_argument("--payload", help="Optional side-effect policy JSON/YAML file merged before setting the class")
    policy_set.add_argument("--stdin", action="store_true", help="Read optional policy JSON from stdin")
    policy_set.add_argument("--project", default=".")
    policy_set.add_argument("--json", action="store_true")

    workflow_parser = subparsers.add_parser("workflow", help="Run guided VerifySignal workflows")
    workflow_sub = workflow_parser.add_subparsers(dest="workflow_command", required=True)
    workflow_run = workflow_sub.add_parser("run")
    workflow_run.add_argument("workflow_id")
    workflow_run.add_argument("--goal", required=True)
    workflow_run.add_argument("--alias")
    workflow_run.add_argument("--integration", choices=["codex", "claude"])
    workflow_run.add_argument("--project", default=".")
    workflow_run.add_argument("--json", action="store_true")
    workflow_resume = workflow_sub.add_parser("resume")
    workflow_resume.add_argument("run_id")
    workflow_resume.add_argument("--project", default=".")
    workflow_resume.add_argument("--json", action="store_true")
    workflow_status = workflow_sub.add_parser("status")
    workflow_status.add_argument("run_id", nargs="?")
    workflow_status.add_argument("--alias", help="Use case alias to inspect without a workflow run id")
    workflow_status.add_argument("--project", default=".")
    workflow_status.add_argument("--json", action="store_true")
    workflow_show = workflow_sub.add_parser("show", help="Show persisted workflow context for a use case")
    workflow_show.add_argument("--alias", required=True, help="Use case alias to inspect")
    workflow_show.add_argument("--project", default=".")
    workflow_show.add_argument("--json", action="store_true")
    workflow_list = workflow_sub.add_parser("list")
    workflow_list.add_argument("--project", default=".")
    workflow_list.add_argument("--json", action="store_true")
    workflow_check = workflow_sub.add_parser("check", help="Check prerequisites for a workflow stage")
    workflow_check.add_argument("stage", help="Workflow stage to check")
    workflow_check.add_argument("--alias", help="Use case alias for stages that target one use case")
    workflow_check.add_argument("--refresh-decision", choices=["accepted", "declined"], help="Record a stale-understanding refresh decision")
    workflow_check.add_argument("--project", default=".")
    workflow_check.add_argument("--json", action="store_true")
    workflow_persist = workflow_sub.add_parser("persist", help="Persist a workflow stage through canonical CLI operations")
    workflow_persist.add_argument("stage", help="Workflow stage to persist")
    workflow_persist.add_argument("--alias", help="Use case alias for use-case stages")
    workflow_persist.add_argument("--scope", help="Understanding inventory scope: all, changed, continue, route:<path>, or area:<name>")
    workflow_persist.add_argument("--payload", help="Path to a JSON/YAML payload outside managed .verifysignal artifacts")
    workflow_persist.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin")
    workflow_persist.add_argument("--project", default=".")
    workflow_persist.add_argument("--json", action="store_true")
    workflow_supersede = workflow_sub.add_parser("supersede-write-outcome", help="Record an owner-approved supersede review for a previous write outcome")
    workflow_supersede.add_argument("--alias", required=True)
    workflow_supersede.add_argument("--payload", help="Path to a JSON/YAML supersede review payload")
    workflow_supersede.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin")
    workflow_supersede.add_argument("--project", default=".")
    workflow_supersede.add_argument("--json", action="store_true")
    workflow_approve_rerun = workflow_sub.add_parser("approve-rerun", help="Record owner approval for a confirmed write rerun")
    workflow_approve_rerun.add_argument("--alias", required=True)
    workflow_approve_rerun.add_argument("--confirm-risk", help="Structured rerun confirmation id from workflow check run")
    workflow_approve_rerun.add_argument("--project", default=".")
    workflow_approve_rerun.add_argument("--json", action="store_true")
    workflow_migrate = workflow_sub.add_parser("migrate", help="Apply an approved workspace migration plan")
    workflow_migrate.add_argument("--approve", required=True, help="Migration id to apply")
    workflow_migrate.add_argument("--project", default=".")
    workflow_migrate.add_argument("--json", action="store_true")
    workflow_recommend = workflow_sub.add_parser("recommend-first-run", help="Recommend the first golden-path run")
    workflow_recommend.add_argument("--project", default=".")
    workflow_recommend.add_argument("--json", action="store_true")
    workflow_accept = workflow_sub.add_parser("accept-first-run", help="Accept the recommended first golden-path run")
    workflow_accept.add_argument("alias")
    workflow_accept.add_argument("--project", default=".")
    workflow_accept.add_argument("--json", action="store_true")
    workflow_skip = workflow_sub.add_parser("skip-first-run", help="Skip the recommended first golden-path run")
    workflow_skip.add_argument("--project", default=".")
    workflow_skip.add_argument("--json", action="store_true")
    workflow_inspect_gp = workflow_sub.add_parser("inspect-golden-path-state", help="Inspect Golden Path workspace state")
    workflow_inspect_gp.add_argument("--project", default=".")
    workflow_inspect_gp.add_argument("--json", action="store_true")
    workflow_reset_gp = workflow_sub.add_parser("reset-golden-path-state", help="Reset Golden Path-owned workspace state")
    workflow_reset_gp.add_argument("--project", default=".")
    workflow_reset_gp.add_argument("--preview", action="store_true")
    workflow_reset_gp.add_argument("--confirm", action="store_true")
    workflow_reset_gp.add_argument("--json", action="store_true")
    workflow_info = workflow_sub.add_parser("info")
    workflow_info.add_argument("workflow_id", nargs="?", default="verifysignal-use-case")
    workflow_info.add_argument("--project", default=".")
    workflow_info.add_argument("--integration", choices=["codex", "claude"])
    workflow_info.add_argument("--json", action="store_true")

    integration_parser = subparsers.add_parser("integration", help="Manage agent integrations")
    integration_sub = integration_parser.add_subparsers(dest="integration_command", required=True)
    integration_list = integration_sub.add_parser("list")
    integration_list.add_argument("--project", default=".")
    integration_list.add_argument("--json", action="store_true")
    for action in ["install", "use", "remove"]:
        child = integration_sub.add_parser(action)
        child.add_argument("key", choices=["codex", "claude"])
        child.add_argument("--project", default=".")
        child.add_argument("--force", action="store_true")
        child.add_argument("--json", action="store_true")
    upgrade = integration_sub.add_parser("upgrade")
    upgrade.add_argument("key", choices=["codex", "claude"], nargs="?")
    upgrade.add_argument("--project", default=".")
    upgrade.add_argument("--force", action="store_true")
    upgrade.add_argument("--json", action="store_true")

    return parser


def create_app() -> argparse.ArgumentParser:
    """Return the CLI application object.

    The implementation uses argparse as a no-network bootstrap fallback while
    the package still declares Typer/Rich as planned dependencies for future
    richer command rendering.
    """
    return create_parser()


def main(argv: list[str] | None = None) -> int:
    parser = create_app()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return EXIT_SUCCESS
    if not args.command:
        parser.print_help()
        return EXIT_SUCCESS
    try:
        result, json_output = dispatch(args)
        emit(result, json_output=json_output)
        return exit_code_for_result(args.command, result)
    except RuntimeInputError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INPUT_MISSING
    except (CoreMissingError, CoreIncompatibleError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CORE_FAILED
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def dispatch(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    command = args.command
    if command == "init":
        project = resolve_project_path(args.project_path, here=args.here)
        return init_command.run(project, args.integration, force=args.force, core_cmd=args.core_cmd, api_base_url=args.api_base_url), args.json
    if command == "check":
        return check_command.run(Path(args.project).resolve(), core_cmd=args.core_cmd, api_base_url=args.api_base_url), args.json
    if command == "author":
        return author_command.run(Path(args.project).resolve(), args.alias, args.description, run_request=args.run_request, skills=args.skill), args.json
    if command == "list":
        return list_command.run(Path(args.project).resolve()), args.json
    if command == "validate":
        return validate_command.run(Path(args.project).resolve(), args.alias, runtime_readiness=args.runtime_readiness, core_cmd=args.core_cmd, api_base_url=args.api_base_url), args.json
    if command == "run":
        return run_command.run(
            Path(args.project).resolve(),
            args.alias,
            profile_name=args.profile,
            interactive=not args.non_interactive,
            core_cmd=args.core_cmd,
            api_base_url=args.api_base_url,
            slow_mo_override=args.slow_mo,
            confirmed_risks=args.confirm_risk,
            record=args.record,
            replay=args.replay,
        ), args.json
    if command == "repair":
        return repair_command.run(Path(args.project).resolve(), args.alias, from_report=args.from_report, approve=args.approve, core_cmd=args.core_cmd, api_base_url=args.api_base_url), args.json
    if command == "discover":
        return discover_command.run(
            Path(args.project).resolve(),
            args.url,
            Path(args.skill),
            core_cmd=args.core_cmd,
            api_base_url=args.api_base_url,
        ), args.json
    if command == "probe":
        return probe_command.run(
            Path(args.project).resolve(),
            Path(args.run_request),
            [Path(skill) for skill in args.skill],
            headed=args.headed,
            slow_mo_ms=args.slow_mo,
            core_cmd=args.core_cmd,
            api_base_url=args.api_base_url,
        ), args.json
    if command == "crystallize":
        return crystallize_command.run(
            Path(args.project).resolve(),
            Path(args.run_dir),
            out=Path(args.out) if args.out else None,
            core_cmd=args.core_cmd,
            api_base_url=args.api_base_url,
        ), args.json
    if command == "core":
        from .core.adapter import CoreAdapter
        from .workspace.repository import get_core_command

        project = Path(args.project).resolve()
        if args.core_command == "version":
            return CoreAdapter(executable=args.core_cmd or get_core_command(project), cwd=project).version(), args.json
        if args.core_command == "setup":
            return core_setup_command.run(project, core_cmd=args.core_cmd, persist=not args.no_persist), args.json
    if command == "policy":
        from .commands import policy as policy_command

        project = Path(args.project).resolve()
        if args.policy_command == "set":
            payload = _load_payload(args) if (args.payload or args.stdin) else None
            return policy_command.set_policy(project, args.alias, side_effect_class=args.policy_class, mode=args.mode, payload=payload), args.json
    if command == "workflow":
        project = Path(args.project).resolve()
        if args.workflow_command == "run":
            return workflow_command.run_workflow(project, args.workflow_id, args.goal, alias=args.alias, integration=args.integration), args.json
        if args.workflow_command == "resume":
            return workflow_command.resume(project, args.run_id), args.json
        if args.workflow_command == "status":
            return workflow_command.status(project, args.run_id, alias=args.alias), args.json
        if args.workflow_command == "show":
            return workflow_command.show(project, args.alias), args.json
        if args.workflow_command == "list":
            return workflow_command.list_runs(project), args.json
        if args.workflow_command == "check":
            return workflow_command.check(project, args.stage, alias=args.alias, refresh_decision=args.refresh_decision), args.json
        if args.workflow_command == "persist":
            return workflow_command.persist(project, args.stage, alias=args.alias, scope=args.scope, payload=_load_payload(args)), args.json
        if args.workflow_command == "supersede-write-outcome":
            return workflow_command.supersede_write_outcome(project, args.alias, payload=_load_payload(args)), args.json
        if args.workflow_command == "approve-rerun":
            return workflow_command.approve_rerun(project, args.alias, confirm_risk=args.confirm_risk), args.json
        if args.workflow_command == "migrate":
            return workflow_command.migrate(project, args.approve), args.json
        if args.workflow_command == "recommend-first-run":
            return workflow_command.recommend_first_run(project), args.json
        if args.workflow_command == "accept-first-run":
            return workflow_command.accept_golden_path_first_run(project, args.alias), args.json
        if args.workflow_command == "skip-first-run":
            return workflow_command.skip_golden_path_first_run(project), args.json
        if args.workflow_command == "inspect-golden-path-state":
            return workflow_command.inspect_golden_path_state(project), args.json
        if args.workflow_command == "reset-golden-path-state":
            return workflow_command.reset_golden_path_state(project, preview=args.preview, confirm=args.confirm), args.json
        if args.workflow_command == "info":
            return workflow_command.info(project, args.workflow_id, integration=args.integration), args.json
    if command == "integration":
        project = Path(args.project).resolve()
        if args.integration_command == "list":
            return integration_command.list_integrations(project), args.json
        if args.integration_command == "install":
            return integration_command.install(project, args.key, force=args.force), args.json
        if args.integration_command == "use":
            return integration_command.use(project, args.key), args.json
        if args.integration_command == "upgrade":
            return integration_command.upgrade(project, args.key, force=args.force), args.json
        if args.integration_command == "remove":
            return integration_command.remove(project, args.key, force=args.force), args.json
    raise ValueError(f"Unsupported command: {command}")


def _emit_mcp(mcp: dict[str, Any] | None) -> None:
    if not mcp:
        return
    if mcp.get("skipped"):
        print(f"Live authoring: .mcp.json left untouched ({mcp.get('reason', 'not safely mergeable')}).")
        return
    print("Live authoring: Playwright MCP written to .mcp.json — approve it in Claude Code on first session.")
    if not mcp.get("nodeAvailable", True):
        print("  warning: Node/npx not found — install Node so the Playwright MCP can run.")


def emit(result: dict[str, Any], json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=False))
        return
    if result.get("onboardingGuide"):
        guide = result["onboardingGuide"]
        print(guide.get("terminalTitle", "VerifySignal Golden Path"))
        print("=======================")
        print(guide.get("terminalSummary", ""))
        _emit_core_status(guide.get("coreStatus"))
        print("")
        print("Status markers:")
        for marker in guide.get("stageMarkers", []):
            print(f"- {marker}")
        print("")
        print("Safety:")
        for item in guide.get("safetyBoundaries", []):
            print(f"- {item}")
        print("")
        print("Success:")
        for item in guide.get("successSemantics", []):
            print(f"- {item}")
        print("")
        print(f"Guide: {guide.get('generatedGuidePath')}")
        print(f"Next: {guide.get('nextCommand')}")
        _emit_mcp(result.get("mcp"))
        return
    if result.get("upgraded") and any(item.get("onboardingGuide") for item in result.get("upgraded", [])):
        print("VerifySignal integration upgrade")
        print("===============================")
        for item in result.get("upgraded", []):
            guide = item.get("onboardingGuide", {})
            core = guide.get("coreStatus", {})
            core_marker = f" | Core {core.get('statusMarker')}" if core else ""
            print(f"- {item.get('integration', {}).get('key')}: {guide.get('generatedGuidePath')} | next {guide.get('nextCommand')}{core_marker}")
            _emit_mcp(item.get("mcp"))
        return
    if "useCases" in result:
        for item in result["useCases"]:
            current = item.get("current") or {}
            presentation = current.get("presentation") or {}
            icon = presentation.get("icon") or ""
            # Show current READINESS (with its lock/severity icon), not just lifecycle status —
            # a locked ceiling reads as trusted, amber/red as needing attention.
            readiness = current.get("status") or item.get("status") or item.get("runnableStatus", "-")
            print(f"{item.get('alias', '-'):<28} {icon:<2} {readiness:<24} {item.get('title', '')}")
            next_action = current.get("nextAction")
            if next_action:
                print(f"{'':<28}    -> {next_action}")
        for warning in result.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
        return
    if "workspacePath" in result:
        print(f"Workspace: {result['workspacePath']}")
        print(f"Integration: {result['integration']}")
        print(f"Core: {result['core'].get('message')}")
        print(result.get("next", ""))
        return
    if "status" in result and "workspace" in result:
        print(f"Status: {result['status']}")
        print(f"Workspace: {result['workspace']['path']}")
        print(f"Core: {result['core'].get('message')}")
        return
    if result.get("schemaVersion") in {
        "verifysignal-spec-workflow-prerequisite-check/v1",
        "verifysignal-spec-workflow-capability/v1",
    }:
        print(f"Stage: {result['stage']}")
        print(f"Status: {result['status']}")
        print(f"Can proceed: {str(result['canProceed']).lower()}")
        if result.get("useCaseAlias"):
            print(f"Alias: {result['useCaseAlias']}")
        if result.get("missingArtifacts"):
            print("Missing:")
            for path in result["missingArtifacts"]:
                print(f"- {path}")
        if result.get("staleReasons"):
            print("Stale reasons:")
            for reason in result["staleReasons"]:
                print(f"- {reason.get('code')}: {reason.get('message')}")
        for warning in result.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
        if result.get("nextCommand"):
            print(f"Next: {result['nextCommand']}")
        if result.get("onboardingPreparation"):
            prep = result["onboardingPreparation"]
            print("Onboarding preparation:")
            print(f"- status: {prep.get('status')}")
            print(f"- approval required: {str(prep.get('approvalRequired')).lower()}")
            if prep.get("summary"):
                print(f"- summary: {prep.get('summary')}")
            if result.get("resumeCommand"):
                print(f"Resume: {result['resumeCommand']}")
        return
    if result.get("schemaVersion") == "verifysignal-spec-workflow-stage-persistence-result/v1":
        print(f"Stage: {result['stage']}")
        print(f"Status: {result['status']}")
        if result.get("alias"):
            print(f"Alias: {result['alias']}")
        for blocker in result.get("blockers", []):
            print(f"blocker: {blocker.get('code')}: {blocker.get('message')}", file=sys.stderr)
        if result.get("nextCommand"):
            print(f"Next: {result['nextCommand']}")
        return
    if result.get("schemaVersion") == "verifysignal-spec-validation-readiness/v1":
        print(f"Status: {result['status']}")
        print(f"Structural: {result.get('structuralValidation', {}).get('status')}")
        print(f"Core: {result.get('coreReadiness', {}).get('status')}")
        for blocker in result.get("blockers", []):
            print(f"blocker: {blocker.get('code')}: {blocker.get('message')}", file=sys.stderr)
        return
    if result.get("schemaVersion") == "verifysignal-spec-core-setup/v1":
        _emit_core_setup_result(result)
        return
    if result.get("schemaVersion") == "verifysignal-spec-first-run-recommendation/v1":
        print("VerifySignal Golden Path")
        print("=======================")
        print(f"Status: {result.get('status')}")
        if result.get("recommendedCandidate"):
            candidate = result["recommendedCandidate"]
            print(f"[RECOMMENDED] {candidate.get('alias')}")
            print(result.get("recommendationText", ""))
            if candidate.get("idealCriteriaMissing"):
                print(f"Missing ideal criteria: {', '.join(candidate.get('idealCriteriaMissing', []))}")
        if result.get("branchRelevantCandidates"):
            print("Branch-relevant candidates:")
            for item in result["branchRelevantCandidates"]:
                print(f"- {item.get('candidateAlias')}: {item.get('branchRelevanceReason', 'branch relevant')}")
        if result.get("acceptancePrompt"):
            print(result["acceptancePrompt"])
        if result.get("nextAction"):
            print(f"Next: {result['nextAction']}")
        return
    if result.get("schemaVersion") == "verifysignal-spec-guided-first-run/v1":
        print("VerifySignal Guided First Run")
        print("============================")
        print(f"Status: {result.get('status')}")
        print(f"Stage: {result.get('stage')}")
        if result.get("selectedCandidate"):
            print(f"Selected: {result.get('selectedCandidate')}")
        for card in result.get("stageCards", []):
            print(f"{card.get('statusMarker')} {card.get('title')}: {card.get('summary')}")
        if result.get("resumeCommand"):
            print(f"Resume: {result['resumeCommand']}")
        elif result.get("nextAction"):
            print(f"Next: {result['nextAction']}")
        return
    print(json.dumps(result, indent=2, sort_keys=False))


def _emit_core_status(core_status: dict[str, Any] | None) -> None:
    if not core_status:
        return
    print("")
    print(f"VerifySignal Core: {core_status.get('statusMarker')}")
    marker = core_status.get("statusMarker")
    if marker == "[READY]":
        print(f"Source: {core_status.get('source')}")
        print(f"Command: {core_status.get('coreCommand')}")
    else:
        print(core_status.get("summary", ""))
    print(f"Next: {core_status.get('nextAction')}")


def _emit_core_setup_result(result: dict[str, Any]) -> None:
    markers = {
        "ready": "[READY]",
        "missing": "[BLOCKED]",
        "incompatible": "[INCOMPATIBLE]",
        "error": "[ERROR]",
    }
    print("VerifySignal Core setup")
    print("======================")
    print(f"Status: {markers.get(result.get('status'), '[ERROR]')}")
    print(result.get("message", ""))
    if result.get("source"):
        print(f"Source: {result.get('source')}")
    if result.get("coreCommand"):
        print(f"Command: {result.get('coreCommand')}")
    if result.get("persisted"):
        print("Persisted: true")
    if result.get("oneTime"):
        print("One-time: true")
    if result.get("attempts"):
        print("Attempts:")
        for attempt in result.get("attempts", []):
            print(f"- {attempt.get('source')}: {attempt.get('status')} {attempt.get('command')}")
    next_action = result.get("nextAction")
    if result.get("status") != "ready":
        next_action = result.get("recoveryCommand") or next_action
    print(f"Next: {next_action}")


def exit_code_for_result(command: str, result: dict[str, Any]) -> int:
    status = result.get("status")
    if command == "core" and result.get("schemaVersion") == "verifysignal-spec-core-setup/v1":
        return EXIT_SUCCESS
    if command == "check" and status != "passed":
        return EXIT_VALIDATION_FAILED
    # A repair signals "action required" (exit 4) unless a deterministic mutation was actually
    # applied. `conflict` is a blocked repair that was `--approve`d but applied nothing
    # (readyForRun=False) — it must not report success to CI just because the flag was set.
    if command == "repair" and result.get("repair", {}).get("approvalStatus") in {"pending", "proposed", "conflict"}:
        return EXIT_APPROVAL_REQUIRED
    # A mutation was applied but revalidation either FAILED (artifact still does not pass) or could not
    # RUN at all (crashed → "not-run"). Neither proves the gap closed, so both are validation failures
    # (exit 2), never a silent success.
    if command == "repair" and result.get("repair", {}).get("approvalStatus") in {"revalidation-failed", "revalidation-unavailable"}:
        return EXIT_VALIDATION_FAILED
    if status in {"blocked", "error", "failed", "incomplete"}:
        return EXIT_VALIDATION_FAILED
    return EXIT_SUCCESS


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.payload) == bool(args.stdin):
        raise ValueError("Use exactly one of --payload or --stdin.")
    if args.payload:
        from .workspace.repository import load_document

        path = Path(args.payload).resolve()
        if f"{Path(args.project).resolve() / '.verifysignal'}" in str(path):
            raise ValueError("Payload file must be outside managed .verifysignal artifacts.")
        payload = load_document(path, default={})
        if not isinstance(payload, dict):
            raise ValueError("Workflow persistence payload must be an object.")
        return payload
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        raise ValueError("Workflow persistence payload must be an object.")
    return payload


def _program_name() -> str:
    name = Path(sys.argv[0]).name
    if name in {"verifysignal", "verifysignal-spec"}:
        return name
    return "verifysignal"
