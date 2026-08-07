"""RATCHET (the Windows leg of the per-repo gate).

Every other job in every VerifySignal repo runs on ubuntu, which is exactly why Windows was the one
platform that broke: nobody had ever run it. A real user hit ``platform.unsupported`` on
``verifysignal init`` after the landing page began advertising ``scripts/install.ps1``.

The value of this job is entirely in WHAT it runs, so it is pinned as text:

- it runs on a Windows runner. A Windows leg on ubuntu proves nothing.
- it installs through ``scripts/install.ps1`` -- the advertised customer path -- and with ``-From``
  pointing at the checkout, so the code under review is what gets installed. Without ``-From`` the
  job would prove that PyPI works, not that the pull request does.
- it exercises ``setup-playwright-mcp``, the first and only exercise anywhere of the ``.cmd`` branch
  in ``_playwright_mcp_executable`` and of the ``sys.platform == "win32"`` bypass of the
  ``os.access(X_OK)`` check.
- it does NOT run pytest. The suite's fixtures are shebang scripts; the decided scope is that the
  Windows leg proves the CUSTOMER path and that contributing still requires mac or Linux. A future
  edit adding pytest here would look like more coverage and would in fact be a scope change.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _windows_job() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "  windows-install:" in text, "the Windows leg of the gate is gone"
    return text[text.index("  windows-install:") :]


def _workflow_jobs() -> dict[str, object]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = document.get("jobs") if isinstance(document, dict) else None
    assert isinstance(jobs, dict), "ci.yml must declare jobs"
    return jobs


def _run_scripts(job: object) -> str:
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    return "\n".join(
        str(step.get("run", ""))
        for step in steps
        if isinstance(step, dict)
    )


def _result_reference(job_id: str) -> tuple[str, str]:
    return (f"needs.{job_id}.result", f"needs['{job_id}'].result")


def test_the_windows_leg_runs_on_windows() -> None:
    assert "runs-on: windows-latest" in _windows_job()


def test_the_windows_leg_installs_the_advertised_installer_from_this_checkout() -> None:
    job = _windows_job()
    assert "scripts/install.ps1" in job
    # Without -From this would install the PUBLISHED wheel and pass regardless of the change.
    assert "-From" in job
    assert "GITHUB_WORKSPACE" in job


def test_the_windows_leg_proves_the_cli_and_the_browser_provider() -> None:
    job = _windows_job()
    assert "verifysignal --version" in job
    assert "verifysignal integration setup-playwright-mcp" in job


def test_the_windows_leg_stays_a_customer_path_not_a_contributor_one() -> None:
    # pytest here would be a scope change wearing the costume of more coverage.
    assert "pytest" not in _windows_job()


def test_windows_safety_job_executes_native_authority_primitives() -> None:
    jobs = _workflow_jobs()
    safety = jobs.get("windows-safety")
    assert isinstance(safety, dict), "native Windows safety coverage is gone"
    assert safety.get("runs-on") == "windows-latest"
    scripts = _run_scripts(safety)
    assert "python -m pytest -q" in scripts
    for module in (
        "tests/unit/test_run_invocation_lock.py",
        "tests/unit/test_durable_run_persistence.py",
        "tests/unit/test_authority_path_safety.py",
        "tests/unit/test_run_request_preparation.py",
    ):
        assert module in scripts


def test_branch_protected_spec_context_aggregates_ubuntu_and_windows() -> None:
    jobs = _workflow_jobs()
    aggregator = jobs.get("spec")
    assert isinstance(aggregator, dict), "the protected spec context must remain a job"

    raw_needs = aggregator.get("needs")
    if isinstance(raw_needs, str):
        needs = {raw_needs}
    else:
        assert isinstance(raw_needs, list), "spec must aggregate prerequisite jobs"
        needs = {str(item) for item in raw_needs}

    assert {"windows-install", "windows-safety"} <= needs
    ubuntu_needs = [
        job_id
        for job_id in needs
        if isinstance(jobs.get(job_id), dict)
        and jobs[job_id].get("runs-on") == "ubuntu-latest"  # type: ignore[union-attr]
        and "python -m pytest -q" in _run_scripts(jobs[job_id])
    ]
    assert len(ubuntu_needs) == 1, "spec must depend on the Ubuntu pytest job"

    # A normal dependent job is skipped when a prerequisite fails. Required
    # contexts need an always-running aggregator that turns either result into
    # a failure instead of allowing a skipped green check.
    assert "always()" in str(aggregator.get("if", ""))
    aggregator_text = str(aggregator)
    for prerequisite in (ubuntu_needs[0], "windows-safety", "windows-install"):
        assert any(
            reference in aggregator_text
            for reference in _result_reference(prerequisite)
        )
    assert "success" in aggregator_text
