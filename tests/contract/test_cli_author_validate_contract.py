from __future__ import annotations

import json

from helpers import FAKE_CORE, CliTestCase


class AuthorValidateContractTests(CliTestCase):
    def test_author_and_validate_json(self) -> None:
        self.assertEqual(
            self.cli(
                [
                    "init",
                    str(self.project),
                    "--integration",
                    "codex",
                    "--core-cmd",
                    str(FAKE_CORE),
                ]
            )[0],
            0,
        )
        code, out, err = self.cli(["author", "login", "Validate login.", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["alias"], "login")
        self.assertTrue(payload["questions"])

        code, out, err = self.cli(["validate", "login", "--project", str(self.project), "--json"])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["status"], "passed")
