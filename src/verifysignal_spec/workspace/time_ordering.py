from __future__ import annotations

import calendar
from datetime import UTC, datetime
import re
from typing import Any


_UTC_ISO_RE = re.compile(
    r"^(?P<whole>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,9}))?"
    r"(?P<zone>Z|[+-]\d{2}:\d{2})?$"
)


def parse_utc_iso_ns(value: Any) -> int | None:
    """Parse a supported ISO timestamp without discarding nanoseconds."""

    if not isinstance(value, str) or not value:
        return None
    match = _UTC_ISO_RE.fullmatch(value)
    if match is None:
        return None
    zone = match.group("zone") or "+00:00"
    normalized_zone = "+00:00" if zone == "Z" else zone
    try:
        parsed = datetime.fromisoformat(
            f"{match.group('whole')}{normalized_zone}"
        ).astimezone(UTC)
    except ValueError:
        return None
    seconds = calendar.timegm(parsed.timetuple())
    fraction = match.group("fraction") or ""
    nanoseconds = int(fraction.ljust(9, "0")) if fraction else 0
    return seconds * 1_000_000_000 + nanoseconds


def format_utc_ns(value: int) -> str:
    """Format an epoch nanosecond value as canonical UTC ISO text."""

    seconds, nanoseconds = divmod(value, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{prefix}.{nanoseconds:09d}Z"
