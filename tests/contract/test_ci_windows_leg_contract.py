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

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _windows_job() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "  windows-install:" in text, "the Windows leg of the gate is gone"
    return text[text.index("  windows-install:") :]


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
