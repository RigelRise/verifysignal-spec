from __future__ import annotations

from helpers import CliTestCase

from verifysignal_spec.workspace import artifacts
from verifysignal_spec.workspace.models import ArtifactReference, UseCaseRecord
from verifysignal_spec.workspace.models import RuntimeInputRequirement
from verifysignal_spec.workspace.repository import init_workspace, save_use_case
from verifysignal_spec.workspace.validation import validate_workspace
from verifysignal_spec.workspace.validation import validate_session_ref


class WorkspaceModelTests(CliTestCase):
    def test_use_case_schema_and_external_reference_validation(self) -> None:
        init_workspace(self.project)
        record = UseCaseRecord(
            alias="login",
            title="Login",
            description="Login",
            runRequest=artifacts.link_external_artifact("external/login.yaml", "run-request"),
            mainSkill=artifacts.link_external_artifact("external/login.browser.md", "skill"),
            skills=[artifacts.link_external_artifact("external/login.browser.md", "skill")],
        )
        (self.project / "external").mkdir()
        (self.project / "external" / "login.yaml").write_text("schemaVersion: qa-run-request/v1\n", encoding="utf-8")
        (self.project / "external" / "login.browser.md").write_text("---\nschemaVersion: qa-skill/v1\n---\n", encoding="utf-8")
        save_use_case(self.project, record)

        findings = validate_workspace(self.project)
        self.assertFalse([item for item in findings if item["severity"] == "blocking"])

    def test_secret_policy_rejects_persisted_secret_values(self) -> None:
        init_workspace(self.project)
        record = UseCaseRecord(
            alias="login",
            title="Login",
            description="Login",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/login.yaml", kind="run-request"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/login.browser.md", kind="skill"),
            skills=[ArtifactReference(path=".verifysignal/skills/login.browser.md", kind="skill")],
            validation={"token": "fake-credential-value-abcdefghijklmnop"},
        )
        artifacts.write_generated_artifacts(self.project, record)
        save_use_case(self.project, record)

        findings = validate_workspace(self.project)
        self.assertTrue(any(item["code"] == "secret-looking-value" for item in findings))

    def test_nested_workspace_findings_report_posix_paths(self) -> None:
        # The scanned-directory branch of validate_workspace builds its finding path by hand. It was
        # the one place in the codebase that stringified a Path instead of calling .as_posix(), so a
        # nested file on Windows produced a mixed separator (`.verifysignal/readiness/sub\hint.yaml`)
        # in public output. This pins the contract; the Windows CI leg is what can observe the break.
        init_workspace(self.project)
        nested = self.project / ".verifysignal" / "readiness" / "sub"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "hint.yaml").write_text("token: fake-credential-value-abcdefghijklmnop\n", encoding="utf-8")

        paths = [item["path"] for item in validate_workspace(self.project) if item["code"] == "secret-looking-value"]

        self.assertTrue(any(item.startswith(".verifysignal/readiness/sub/hint.yaml") for item in paths), paths)
        self.assertEqual([], [item for item in paths if "\\" in item])

    def test_generated_artifacts_use_core_compliant_skill_envelopes(self) -> None:
        init_workspace(self.project)
        record = UseCaseRecord(
            alias="login",
            title="Login",
            description="Validate login.",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/login.yaml", kind="run-request", id="request.login"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/login.browser.md", kind="skill", id="skill.login"),
            skills=[ArtifactReference(path=".verifysignal/skills/login.browser.md", kind="skill", id="skill.login")],
            runtimeInputs=[RuntimeInputRequirement(name="baseUrl")],
        )
        artifacts.write_generated_artifacts(self.project, record, overwrite=True)
        run_request = (self.project / ".verifysignal/run-requests/login.yaml").read_text()
        skill = (self.project / ".verifysignal/skills/login.browser.md").read_text()
        self.assertIn('"schemaVersion": "qa-run-request/v1"', run_request)
        self.assertIn('"parameters"', run_request)
        self.assertIn("schemaVersion: qa-skill/v1", skill)
        self.assertIn("browser:", skill)
        self.assertIn("value: \"{{parameters.baseUrl}}\"", skill)

    def test_use_case_serializes_source_only_skills_and_composition_decisions(self) -> None:
        record = UseCaseRecord(
            alias="brands-search-authenticated",
            title="Brands Search Authenticated",
            description="Validate authenticated brands search.",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/brands.yaml", kind="run-request"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/brands-main.browser.md", kind="skill", id="skill.brands-main"),
            skills=[
                ArtifactReference(path=".verifysignal/skills/brands-main.browser.md", kind="skill", id="skill.brands-main"),
                ArtifactReference(path=".verifysignal/skills/login.browser.md", kind="skill", id="skill.login"),
            ],
            sourceOnlySkills=[
                ArtifactReference(path=".verifysignal/skills/login.browser.md", kind="skill", id="skill.login"),
            ],
            skillComposition={
                "mode": "inline-into-main",
                "sourceSkillPaths": [".verifysignal/skills/login.browser.md"],
                "mainSkillPath": ".verifysignal/skills/brands-main.browser.md",
                "credentialReferencePolicy": "preserve-placeholders",
            },
        )

        restored = UseCaseRecord.from_dict(record.to_dict())

        self.assertEqual(restored.sourceOnlySkills[0].path, ".verifysignal/skills/login.browser.md")
        self.assertEqual(restored.skillComposition["mode"], "inline-into-main")

    def test_session_reference_round_trips_and_renders_without_session_material(self) -> None:
        record = UseCaseRecord(
            alias="authenticated-project",
            title="Authenticated Project",
            description="Reach a protected project form.",
            runRequest=ArtifactReference(path=".verifysignal/run-requests/project.yaml", kind="run-request"),
            mainSkill=ArtifactReference(path=".verifysignal/skills/project.browser.md", kind="skill", id="skill.project"),
            skills=[ArtifactReference(path=".verifysignal/skills/project.browser.md", kind="skill", id="skill.project")],
            sessionRef={"source": "environment", "key": "VS_AUTH_STORAGE_STATE"},
        )

        restored = UseCaseRecord.from_dict(record.to_dict())
        rendered = artifacts.render_run_request(restored)

        self.assertEqual(restored.sessionRef, {"source": "environment", "key": "VS_AUTH_STORAGE_STATE"})
        self.assertIn('"sessionRef"', rendered)
        self.assertIn('"key": "VS_AUTH_STORAGE_STATE"', rendered)
        self.assertNotIn("cookies", rendered)
        self.assertNotIn("origins", rendered)

    def test_session_reference_validation_accepts_public_sources_and_rejects_material(self) -> None:
        self.assertEqual(
            validate_session_ref({"source": "environment", "key": "VS_AUTH_STORAGE_STATE"}),
            [],
        )
        self.assertEqual(
            validate_session_ref({"source": "local-config", "key": "session.path"}),
            [],
        )
        findings = validate_session_ref(
            {
                "source": "environment",
                "key": "VS_AUTH_STORAGE_STATE",
                "cookies": [{"name": "session", "value": "must-not-persist"}],
            }
        )
        self.assertTrue(any(item["code"] == "session-ref-material-forbidden" for item in findings))
