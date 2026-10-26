"""Print `--ignore-vuln` arguments for the dated runtime-advisory exceptions.

Each non-comment line of security/runtime-advisory-exceptions.txt reads
`ADVISORY-ID owner added expires reason...` with ISO dates. A line that is malformed,
expired, not yet added or valid for more than 90 days fails the release gate instead of
being ignored.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import re
import sys

MAX_DAYS = 90
ADVISORY_ID = re.compile(r"[A-Z]+-[0-9A-Za-z-]+")


def ignore_args(text: str, today: date) -> list[str]:
    args: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            advisory, _owner, added, expires, _reason = line.split(maxsplit=4)
            start, end = date.fromisoformat(added), date.fromisoformat(expires)
        except ValueError as error:
            raise ValueError(
                f"line {number}: want ADVISORY-ID owner added expires reason ({error})"
            ) from error
        if not (
            ADVISORY_ID.fullmatch(advisory) and start <= today <= end <= start + timedelta(MAX_DAYS)
        ):
            raise ValueError(
                f"line {number}: {advisory!r} needs an advisory id and "
                f"added <= today <= expires <= added + {MAX_DAYS} days (today is {today})"
            )
        args.append(f"--ignore-vuln={advisory}")
    return args


def main(path: str) -> int:
    try:
        args = ignore_args(Path(path).read_text(encoding="utf-8"), datetime.now(UTC).date())
    except (OSError, ValueError) as error:
        print(f"runtime advisory exceptions: {error}", file=sys.stderr)
        return 1
    print(" ".join(args))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/runtime_audit_args.py <exceptions-file>")
    raise SystemExit(main(sys.argv[1]))
