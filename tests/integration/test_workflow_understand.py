from __future__ import annotations

from verifysignal_spec.workspace.repository import init_workspace
from verifysignal_spec.workflows.engine import create_workflow_run


def test_understand_creates_global_context_and_snapshot(tmp_path) -> None:
    init_workspace(tmp_path)
    run = create_workflow_run(tmp_path, "Validate login.", alias="login", integration="codex")
    assert run.currentStage == "specify"
    assert run.nextCommand == "$verifysignal-specify login"
    assert run.stageStates[0].stage == "understand"
    assert run.stageStates[0].status == "completed"
    assert (tmp_path / ".verifysignal" / "workflows" / "understanding.md").exists()
    assert (tmp_path / ".verifysignal" / "workflows" / "use-cases" / "login" / "understanding.md").exists()
