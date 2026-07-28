from __future__ import annotations

from helpers import agent_template, assert_guardrail_template


def test_all_agent_command_templates_include_guardrail_contract() -> None:
    for stage in ["understand", "specify", "clarify", "plan", "tasks", "implement", "validate", "list", "run", "repair"]:
        assert_guardrail_template(agent_template(stage), stage)


def test_validate_template_mentions_structural_validation_and_core_requirement() -> None:
    content = agent_template("validate")
    assert "structuralValidation" in content
    assert "VerifySignal Core is required for the complete VerifySignal validation and browser execution experience" in content
    assert "runtime readiness verifies target resolution, target reachability, required runtime prerequisites, and Core authoring readiness" in content
    assert "verifysignal workflow migrate --approve <migration-id> --json" in content
    assert "Treat `workflow check validate` as structural readiness only" in content
    assert "does not validate protected-runtime entitlement readiness" in content
    assert "follow its `nextAction` exactly" in content


def test_validate_does_not_loop_setup_for_key_unknown_entitlement() -> None:
    content = agent_template("validate")
    assert "`entitlement.key-unknown`" in content
    assert "do not rerun `init`, `init --force`, or `core setup`" in content
    assert "use that blocker's exact `recoveryCommand`" in content


def test_implement_template_uses_canonical_skill_shape_and_cli_persistence() -> None:
    content = agent_template("implement")
    assert ".verifysignal/skills/<name>.browser.md" in content
    assert "verifysignal workflow persist implement" in content
    assert "never manually author registry entries" in content
    assert "Do not use `verifysignal author`" in content
    assert "the CLI owns the final `qa-run-request/v1` and `qa-skill/v1` envelopes" in content
    assert "intent.browser.steps" in content
    assert "browserAuthoringContract" in content
    assert "`navigate` uses `value`" in content
    assert "intent.browser.targets" in content
    assert "Run `verifysignal validate <alias> --runtime-readiness` before reporting browser artifacts ready" in content


def test_plan_and_implement_templates_do_not_author_from_hardcoded_core_lists() -> None:
    plan = agent_template("plan")
    implement = agent_template("implement")

    assert "coreExecutableContract" in plan
    assert "Core-declared public network match keys" in plan
    assert "browserAuthoringContract" in implement
    assert "non-authoritative examples" in implement
    assert "public match keys such as `urlContains`, `status`, `requestBodyContains`, or `responseBodyContains`" not in plan
    assert "one primary selector signal (`testId`, `label`, `text`, `css`, `semanticLocator`, or `all`)" not in implement


def test_specify_and_plan_templates_require_browser_target_before_executable_planning() -> None:
    specify = agent_template("specify")
    plan = agent_template("plan")
    assert "Browser validation use cases require a resolved target application environment before executable planning" in specify
    assert "Do not leave `baseUrl` or equivalent target parameters empty after the user has supplied a target" in plan


def test_plan_template_makes_main_skill_executable() -> None:
    content = agent_template("plan")
    assert "Make the main skill executable by Core for the complete planned validation path" in content
    assert "workflow show --alias <alias> --json" in content


def test_run_template_forbids_summarizing_incomplete_runs_as_passed() -> None:
    content = agent_template("run")
    assert "Core `passed` result can still be `coverageStatus: incomplete`" in content
    assert "Do not summarize `status: incomplete` as passed" in content


def test_run_template_uses_single_outcome_summary_without_manual_gate_tables() -> None:
    content = agent_template("run")
    assert "Use `runOutcomeSummary` as the primary source for the final user-facing run result" in content
    assert "Render exactly one final run result section" in content
    assert "Do not build markdown tables from `gateCoverage`" in content
    assert "Do not repeat gate coverage" in content


def test_auto_loop_documents_mcp_capability_selfcheck_and_fallback() -> None:
    content = agent_template("auto")
    assert "Playwright MCP" in content
    assert "self-check" in content
    assert "author from source" in content  # graceful fallback when no MCP
    assert "discover" in content and "wins" in content  # discover beats MCP on disagreement
    assert "ref=" in content  # MCP refs are per-snapshot, not a selector signal
    assert "commitStepId" in content  # live exploration stops before the write commit
    assert "MCP accessibility snapshots" in content or "Never persist or print MCP" in content


def test_repair_template_documents_mcp_readonly_investigation() -> None:
    content = agent_template("repair")
    assert "Playwright MCP" in content
    assert "read-only" in content.lower()
    assert "discover" in content  # discover confirms the repair, not the MCP
    assert "MCP accessibility snapshots" in content  # extended no-persist list


def test_browser_templates_preserve_selector_and_side_effect_safety_feedback() -> None:
    implement = agent_template("implement")
    validate = agent_template("validate")
    run = agent_template("run")
    repair = agent_template("repair")

    assert "Do not hide an ambiguous locator with `.first()` or `:visible`" in implement
    assert "Do not add a broad `/graphql` allow rule merely because the endpoint uses POST" in implement

    assert "`authoringWarnings`" in validate
    assert "`degenerate-text-target`" in validate
    assert "`unstable-generated-css-target`" in validate
    assert "must block runtime readiness before browser navigation" in validate

    assert "A side-effect policy violation makes the Spec run failed" in run
    assert "Only a later clean rerun can restore `strictPass: true`" in run

    assert "Never automatically change `sideEffects.class`, `sideEffects.mode`, `allowed`, or `forbidden`" in repair
    assert "Never add an allow rule merely to make an observed request pass" in repair


def test_auto_loop_mcp_credential_safety() -> None:
    content = agent_template("auto")
    assert "storage-state" in content
    assert "environment" in content.lower()
    assert "never persist" in content.lower()
