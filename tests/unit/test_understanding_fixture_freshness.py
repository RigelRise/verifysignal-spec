"""RATCHET (self-expiring fixtures). `browser_understanding_payload` stands for a RECENT product
understanding: every test built on it asserts `check_prerequisites(...) == "ready"`. Its timestamp
was a written-out date, `2026-07-26T18:00:00Z`, which does not mean "recent" — it means "recent for
a while". WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS is 7, so on 2026-08-02 the fixture crossed the window
and two tests started failing on a tree where nothing had changed. The product was right; the
fixture was asserting against the calendar. Every commit after that date was red, and the failure
pointed at the staleness code instead of at the fixture.

Two guards, because they fail at different times:
  - the VALUE must sit inside the freshness window. This is the behaviour the dependent tests rely
    on, and it is what breaks when a date expires;
  - the ASSIGNMENT must be derived from the clock, not written out. This fails the moment someone
    re-hardcodes a date, instead of a week later on an unrelated pull request.
"""

from __future__ import annotations

import re

from datetime import UTC, datetime, timedelta
from pathlib import Path

from verifysignal_spec.workflows.models import WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS

from tests.fixtures.workflows import browser_first_understanding
from tests.fixtures.workflows.browser_first_understanding import OBSERVED_AT

FIXTURE_SOURCE = Path(browser_first_understanding.__file__)


def test_the_fixture_timestamp_is_inside_the_freshness_window() -> None:
    observed = datetime.strptime(OBSERVED_AT, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    age = datetime.now(UTC) - observed

    assert age >= timedelta(0), f"the fixture is stamped in the future: {OBSERVED_AT}"
    # Strictly inside: prerequisites.py treats `age >= timedelta(days=MAX_AGE)` as stale, so a
    # fixture sitting exactly on the boundary would flip with the second it happens to run at.
    assert age < timedelta(days=WORKFLOW_UNDERSTANDING_MAX_AGE_DAYS), (
        f"the understanding fixture is {age.days} days old and reads as stale; the tests that use it "
        "assert 'ready'"
    )


def test_the_fixture_timestamp_is_computed_rather_than_written_out() -> None:
    source = FIXTURE_SOURCE.read_text(encoding="utf-8")
    assignment = re.search(r"^OBSERVED_AT\s*=\s*(.+)$", source, flags=re.MULTILINE)
    assert assignment is not None, "OBSERVED_AT disappeared from the fixture"

    assert not re.match(r"""['"]\d{4}-\d{2}-\d{2}""", assignment.group(1).strip()), (
        "OBSERVED_AT is a hardcoded date again. It expires on its own: pin it to the clock "
        "(datetime.now(UTC) - timedelta(...)) so the fixture keeps meaning 'recent'."
    )
    assert "datetime.now" in assignment.group(1)
