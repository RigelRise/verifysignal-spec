from __future__ import annotations

from verifysignal_spec.workflows.engine import create_workflow_run
from verifysignal_spec.workflows.stage_persistence import persist_stage
from verifysignal_spec.workflows.transitions import transition_workflow
from verifysignal_spec.workspace.repository import init_workspace, load_document
from tests.helpers import FAKE_CORE


def _confirm_target(project, alias: str, url: str = "https://app.example.test") -> None:
    result = persist_stage(
        project,
        "clarify",
        alias=alias,
        payload={
            "answers": [
                {
                    "questionId": "browser-target-environment",
                    "answerSummary": url,
                    "confirmationSource": "direct-user",
                }
            ]
        },
    )
    assert result["status"] == "persisted"


def _start_workflow(project, alias: str) -> None:
    create_workflow_run(
        project,
        f"Validate {alias}.",
        alias=alias,
        integration="codex",
    )


def _advance_from_clarify_to_implement(project, alias: str) -> None:
    transition_workflow(
        project,
        alias,
        stage="clarify",
        outcome="completed",
    )
    transition_workflow(
        project,
        alias,
        stage="plan",
        outcome="completed",
    )
    transition_workflow(
        project,
        alias,
        stage="tasks",
        outcome="completed",
    )


def test_persistence_rejects_secret_looking_payload_values(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    result = persist_stage(
        project,
        "specify",
        alias="login",
        payload={
            "alias": "login",
            "surface": "/login",
            "behavior": "Validate login.",
            "expectedOutcome": "Dashboard.",
            "customSourceReason": "Fixture.",
            "password": "super-secret-value",
        },
    )
    assert result["status"] == "invalid"
    assert result["blockers"][0]["code"] == "payload.secret-looking-value"


def test_missing_stage_payload_field_reports_public_contract_recovery(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))

    result = persist_stage(
        project,
        "specify",
        alias="login",
        payload={
            "alias": "login",
            "surface": "/login",
            "behavior": "Validate login.",
            "customSourceReason": "Fixture.",
            "expectedOucome": "Typo.",
        },
    )

    assert result["status"] == "invalid"
    blocker = result["blockers"][0]
    assert blocker["code"] == "payload.missing-required-field"
    assert "stagePayloadContracts.specify.requiredFields" in blocker["documentationRef"]
    assert "workflow info verifysignal-use-case --json" in blocker["recoveryCommand"]
    assert any("expectedOucome" in warning for warning in result["warnings"])


def test_unknown_persistence_stage_is_invalid(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    result = persist_stage(project, "unknown", payload={})
    assert result["status"] == "invalid"
    assert result["blockers"][0]["code"] == "stage.unsupported"


def test_specify_accepts_real_agent_payload_synonyms(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    result = persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "purpose": "Validate people search.",
            "targetSurface": "/search/people",
            "expectedOutcome": ["People cards appear."],
            "customSourceReason": "Selected from a partial inventory.",
        },
    )
    assert result["status"] == "persisted"
    record = load_document(project / ".verifysignal/use-cases/search-people.yaml")
    assert record["targetSurface"] == "/search/people"


def test_plan_accepts_skills_alias_for_reusable_skills(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _confirm_target(project, "search-people")
    result = persist_stage(
        project,
        "plan",
        alias="search-people",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/search-people.yaml"},
            "skills": [{"name": "navigate-to-search"}],
            "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
            "unresolvedBlockingClarifications": [],
        },
    )
    assert result["status"] == "persisted"


def test_plan_accepts_supporting_skills_alias_from_real_agent_payload(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _confirm_target(project, "search-people")
    result = persist_stage(
        project,
        "plan",
        alias="search-people",
        payload={
            "runRequest": ".verifysignal/run-requests/search-people.yaml",
            "mainSkill": ".verifysignal/skills/validate-search-people-flow.browser.md",
            "supportingSkills": [
                ".verifysignal/skills/navigate-to-search.browser.md",
                ".verifysignal/skills/search-and-verify-results.browser.md",
            ],
            "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
            "unresolvedBlockingClarifications": [],
        },
    )
    assert result["status"] == "persisted"
    plan = load_document(project / ".verifysignal/workflows/use-cases/search-people/plan.yaml")
    assert plan["mainSkill"] == ".verifysignal/skills/validate-search-people-flow.browser.md"
    assert ".verifysignal/skills/navigate-to-search.browser.md" in plan["supportingSkills"]


def test_plan_required_gate_intent_change_requires_recorded_reason(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _confirm_target(project, "search-people")
    base_plan = {
        "runRequest": ".verifysignal/run-requests/search-people.yaml",
        "reusableSkills": [".verifysignal/skills/validate-search-people.browser.md"],
        "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
        "validationGates": [{"id": "people-results", "description": "People results render.", "required": True}],
        "unresolvedBlockingClarifications": [],
    }
    assert persist_stage(project, "plan", alias="search-people", payload=base_plan)["status"] == "persisted"

    _start_workflow(project, "search-people")
    transition_workflow(
        project,
        "search-people",
        stage="specify",
        outcome="completed",
    )
    _confirm_target(project, "search-people")
    changed_plan = {**base_plan, "validationGates": [{"id": "people-results", "description": "People results render.", "required": False, "condition": "Results exist"}]}
    blocked = persist_stage(project, "plan", alias="search-people", payload=changed_plan)

    assert blocked["status"] == "blocked"
    assert blocked["blockers"][0]["code"] == "gate-intent.requiredness-change-unconfirmed"

    confirmed = persist_stage(
        project,
        "plan",
        alias="search-people",
        payload={
            **changed_plan,
            "gateIntentChanges": [{"gateId": "people-results", "source": "plan", "reason": "Developer confirmed this gate is conditional."}],
        },
    )
    assert confirmed["status"] == "persisted"


def test_implement_accepts_artifacts_list_and_writes_core_envelopes(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _confirm_target(project, "search-people")
    persist_stage(
        project,
        "plan",
        alias="search-people",
        payload={
            "runRequest": ".verifysignal/run-requests/search-people.yaml",
            "reusableSkills": [".verifysignal/skills/navigate-to-search.browser.md"],
            "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
            "unresolvedBlockingClarifications": [],
        },
    )
    transition_workflow(
        project,
        "search-people",
        stage="tasks",
        outcome="completed",
    )
    result = persist_stage(
        project,
        "implement",
        alias="search-people",
        payload={
            "artifacts": [
                {
                    "path": ".verifysignal/run-requests/search-people.yaml",
                    "kind": "run-request",
                    "content": "alias: search-people\n",
                },
                {
                    "path": ".verifysignal/skills/navigate-to-search.browser.md",
                    "kind": "skill",
                    "content": "# navigate-to-search\n\nNavigate to search.",
                },
            ]
        },
    )
    assert result["status"] == "persisted"
    run_request = (project / ".verifysignal/run-requests/search-people.yaml").read_text()
    skill = (project / ".verifysignal/skills/navigate-to-search.browser.md").read_text()
    assert '"schemaVersion": "qa-run-request/v1"' in run_request
    assert "schemaVersion: qa-skill/v1" in skill
    assert "browser:" in skill


def test_implement_rejects_detailed_skill_intent_without_executable_browser_steps(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _advance_from_clarify_to_implement(project, "search-people")
    result = persist_stage(
        project,
        "implement",
        alias="search-people",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/search-people.yaml"},
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-search-people-flow.browser.md",
                    "kind": "skill",
                    "intent": {
                        "description": "Validate the full search people flow.",
                        "successGate": "All five validation gates pass.",
                        "browser": {"startUrl": "https://app.example.test/search/people"},
                        "steps": [
                            {"id": "navigate", "instructions": "Open search people."},
                            {"id": "happy", "instructions": "Search Jordan and assert cards."},
                        ],
                    },
                }
            ],
        },
    )
    assert result["status"] == "invalid"
    assert "executable browser.steps" in result["blockers"][0]["message"]


def test_implement_preserves_executable_intent_and_runtime_input_values(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _advance_from_clarify_to_implement(project, "search-people")
    result = persist_stage(
        project,
        "implement",
        alias="search-people",
        payload={
            "runRequest": {
                "path": ".verifysignal/run-requests/search-people.yaml",
                "intent": {
                    "runtimeInputs": [
                        {"name": "baseUrl", "value": "https://app.example.test"},
                        {"name": "happyPathQuery", "value": "Jordan"},
                    ]
                },
            },
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-search-people-flow.browser.md",
                    "kind": "skill",
                    "intent": {
                        "description": "Validate the full search people flow.",
                        "successGate": "Both gates pass.",
                        "browser": {
                            "targets": {"results": {"css": "body"}},
                            "steps": [
                                {"id": "open", "action": "navigate", "value": "{{parameters.baseUrl}}/search/people"},
                                {"id": "wait-query", "action": "waitForText", "target": "results", "value": "{{parameters.happyPathQuery}}"},
                            ],
                            "assertions": [
                                {"id": "results-visible", "kind": "visible", "target": "results"}
                            ],
                        },
                        "steps": [
                            {"id": "navigate", "instructions": "Open search people."},
                            {"id": "happy", "instructions": "Search Jordan and assert cards."},
                        ],
                    },
                }
            ],
        },
    )
    assert result["status"] == "persisted"
    run_request = load_document(project / ".verifysignal/run-requests/search-people.yaml")
    skill = (project / ".verifysignal/skills/validate-search-people-flow.browser.md").read_text()
    assert run_request["parameters"]["baseUrl"] == "https://app.example.test"
    assert run_request["parameters"]["happyPathQuery"] == "Jordan"
    assert "wait-query" in skill
    assert "Execution Intent" in skill


def test_implement_persists_credential_refs_without_runtime_credential_parameters(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "add-project")
    persist_stage(
        project,
        "specify",
        alias="add-project",
        payload={
            "alias": "add-project",
            "surface": "/manage/project/add",
            "behavior": "Create a project.",
            "expectedOutcome": "Project page renders.",
            "customSourceReason": "Authenticated fixture.",
        },
    )
    _advance_from_clarify_to_implement(project, "add-project")
    result = persist_stage(
        project,
        "implement",
        alias="add-project",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/add-project.yaml"},
            "credentialRefs": {
                "e2eUser": {
                    "source": "environment",
                    "keys": {"email": "E2E_USER_EMAIL", "password": "E2E_USER_PASSWORD"},
                }
            },
            "runtimeInputs": [
                {"name": "baseUrl", "value": "https://app.example.test"},
                {"name": "userEmail", "kind": "credential", "credentialGroup": "e2eUser", "envVar": "E2E_USER_EMAIL"},
                {"name": "userPassword", "kind": "credential", "credentialGroup": "e2eUser", "envVar": "E2E_USER_PASSWORD"},
            ],
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-add-project-flow.browser.md",
                    "kind": "skill",
                    "browser": {
                        "targets": {"emailInput": {"testId": "email-input"}},
                        "steps": [
                            {"id": "fill-email", "action": "fill", "target": "emailInput", "value": "{{credentials.e2eUser.email}}"}
                        ],
                    },
                }
            ],
        },
    )

    assert result["status"] == "persisted"
    use_case = load_document(project / ".verifysignal/use-cases/add-project.yaml")
    run_request = load_document(project / ".verifysignal/run-requests/add-project.yaml")
    assert use_case["credentialRefs"]["e2eUser"]["keys"]["password"] == "E2E_USER_PASSWORD"
    assert {item["name"] for item in use_case["runtimeInputs"]} == {"baseUrl"}
    assert set(run_request["parameters"]) == {"baseUrl"}
    assert "credentialRefs" in run_request


def test_clarify_accepts_answer_only_payload_for_existing_questions(tmp_path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    persist_stage(
        project,
        "clarify",
        alias="search-people",
        payload={
            "questions": [
                {
                    "id": "q1",
                    "prompt": "Which environment should be used?",
                    "reason": "Runtime target affects execution.",
                    "affects": "runtime",
                    "environmentDependent": True,
                }
            ]
        },
    )

    result = persist_stage(
        project,
        "clarify",
        alias="search-people",
        payload={"answers": [{"questionId": "q1", "answerSummary": "Production: https://app.example.test"}]},
    )

    assert result["status"] == "persisted"
    record = load_document(project / ".verifysignal/use-cases/search-people.yaml")
    assert record["authoringQuestions"][0]["status"] == "answered"
    assert record["authoringQuestions"][0]["answerSummary"] == "Production: https://app.example.test"


def test_implement_rejects_invalid_browser_action_before_core_validation(tmp_path) -> None:
    result = _persist_browser_skill(tmp_path, {"targets": {"page": {"css": "body"}}, "steps": [{"id": "bad", "action": "waitForSelector", "target": "page"}]})

    assert result["status"] == "invalid"
    assert "Unsupported browser step action" in result["blockers"][0]["message"]


def test_implement_rejects_navigate_target_without_value(tmp_path) -> None:
    result = _persist_browser_skill(tmp_path, {"steps": [{"id": "open", "action": "navigate", "target": "https://app.example.test"}]})

    assert result["status"] == "invalid"
    assert "navigate must put the URL in value" in result["blockers"][0]["message"]


def test_implement_rejects_inline_step_target_not_declared_in_browser_targets(tmp_path) -> None:
    result = _persist_browser_skill(
        tmp_path,
        {
            "steps": [
                {"id": "open", "action": "navigate", "value": "https://app.example.test/search/people"},
                {"id": "click-search", "action": "click", "target": "input#search"},
            ]
        },
    )

    assert result["status"] == "invalid"
    assert "target 'input#search' is not declared in browser.targets" in result["blockers"][0]["message"]


def test_implement_rejects_browser_assertion_value_field_for_text_kind(tmp_path) -> None:
    result = _persist_browser_skill(
        tmp_path,
        {
            "targets": {"page": {"css": "body"}},
            "steps": [{"id": "open", "action": "navigate", "value": "https://app.example.test/search/people"}],
            "assertions": [{"id": "a1", "kind": "text", "target": "page", "value": "Results"}],
        },
    )

    assert result["status"] == "invalid"
    assert "browser assertions require expected" in result["blockers"][0]["message"]


def test_implement_rejects_await_network_unknown_match_key(tmp_path) -> None:
    result = _persist_browser_skill(
        tmp_path,
        {
            "steps": [
                {"id": "open", "action": "navigate", "value": "https://app.example.test/search/people"},
                {"id": "wait", "action": "awaitNetwork", "match": {"url": "**/api/people**"}},
            ]
        },
    )

    assert result["status"] == "invalid"
    assert "awaitNetwork.match uses unsupported keys: url" in result["blockers"][0]["message"]


def test_implement_rejects_target_with_multiple_primary_locator_signals(tmp_path) -> None:
    result = _persist_browser_skill(
        tmp_path,
        {
            "targets": {"searchInput": {"label": "Search people", "css": "input#search"}},
            "steps": [
                {"id": "open", "action": "navigate", "value": "https://app.example.test/search/people"},
                {"id": "click", "action": "click", "target": "searchInput"},
            ],
        },
    )

    assert result["status"] == "invalid"
    assert "defines multiple primary selector signals" in result["blockers"][0]["message"]


def _persist_browser_skill(tmp_path, browser: dict) -> dict:
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _advance_from_clarify_to_implement(project, "search-people")
    return persist_stage(
        project,
        "implement",
        alias="search-people",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/search-people.yaml"},
            "skills": [
                {
                    "path": ".verifysignal/skills/validate-search-people-flow.browser.md",
                    "kind": "skill",
                    "intent": {
                        "description": "Validate the search people flow.",
                        "successGate": "The browser flow executes.",
                        "browser": browser,
                    },
                }
            ],
        },
    )


def test_implement_pairs_reordered_skill_content_with_its_own_path(tmp_path) -> None:
    # Regression: when the planned main skill is not first in the authored payload, the
    # references are reordered main-first while the payload keeps its authored order. A
    # positional zip of the two would write the helper's body into the main-skill path.
    project = tmp_path / "repo"
    project.mkdir()
    init_workspace(project, core_cmd=str(FAKE_CORE))
    _start_workflow(project, "search-people")
    helper_path = ".verifysignal/skills/navigate-to-search.browser.md"
    main_path = ".verifysignal/skills/validate-search-people-flow.browser.md"
    persist_stage(
        project,
        "specify",
        alias="search-people",
        payload={
            "alias": "search-people",
            "surface": "/search/people",
            "behavior": "Validate people search.",
            "expectedOutcome": "People cards appear.",
            "customSourceReason": "Fixture.",
        },
    )
    _confirm_target(project, "search-people")
    persist_stage(
        project,
        "plan",
        alias="search-people",
        payload={
            "runRequest": ".verifysignal/run-requests/search-people.yaml",
            "reusableSkills": [helper_path, main_path],
            "mainSkill": main_path,
            "runtimeInputs": [{"name": "baseUrl", "value": "https://app.example.test"}],
            "unresolvedBlockingClarifications": [],
        },
    )
    transition_workflow(
        project,
        "search-people",
        stage="tasks",
        outcome="completed",
    )
    # Helper listed FIRST, planned main SECOND -> forces the main-first reorder.
    result = persist_stage(
        project,
        "implement",
        alias="search-people",
        payload={
            "runRequest": {"path": ".verifysignal/run-requests/search-people.yaml"},
            "skills": [
                {
                    "path": helper_path,
                    "kind": "skill",
                    "intent": {
                        "description": "Navigate to the search surface.",
                        "successGate": "Search page is open.",
                        "browser": {
                            "targets": {"nav": {"css": "#nav"}},
                            "steps": [
                                {"id": "helper-open-step", "action": "navigate", "value": "{{parameters.baseUrl}}/search/people"},
                                {"id": "helper-wait-step", "action": "waitForText", "target": "nav", "value": "Search"},
                            ],
                            "assertions": [{"id": "nav-visible", "kind": "visible", "target": "nav"}],
                        },
                    },
                },
                {
                    "path": main_path,
                    "kind": "skill",
                    "intent": {
                        "description": "Validate the full search people flow.",
                        "successGate": "People cards render.",
                        "browser": {
                            "targets": {"results": {"css": "#results"}},
                            "steps": [
                                {"id": "main-open-step", "action": "navigate", "value": "{{parameters.baseUrl}}/search/people"},
                                {"id": "main-wait-step", "action": "waitForText", "target": "results", "value": "Jordan"},
                            ],
                            "assertions": [{"id": "results-visible", "kind": "visible", "target": "results"}],
                        },
                    },
                },
            ],
        },
    )
    assert result["status"] == "persisted"
    main_file = (project / main_path).read_text()
    helper_file = (project / helper_path).read_text()
    # Each skill's authored content must land at ITS OWN path — never swapped by the reorder.
    assert "main-open-step" in main_file
    assert "helper-open-step" not in main_file
    assert "helper-open-step" in helper_file
    assert "main-open-step" not in helper_file
