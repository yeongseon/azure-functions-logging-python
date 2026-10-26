"""Dated runtime-advisory exceptions must fail the release gate instead of being ignored."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tools import runtime_audit_args

TODAY = date(2026, 10, 24)
ADVISORY = "GHSA-aaaa-bbbb-cccc"


def _line(added: int, expires: int, advisory: str = ADVISORY) -> str:
    """One exception line with dates given as day offsets from TODAY."""
    return f"{advisory} owner {TODAY + timedelta(added)} {TODAY + timedelta(expires)} reason\n"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("", [], id="empty"),
        pytest.param("# note\n\n   \n", [], id="comments-and-blank-lines"),
        pytest.param(_line(-10, 30), [f"--ignore-vuln={ADVISORY}"], id="current"),
        pytest.param(_line(-1, 0), [f"--ignore-vuln={ADVISORY}"], id="expires-today"),
        pytest.param(_line(0, 90), [f"--ignore-vuln={ADVISORY}"], id="exactly-90-days"),
        pytest.param(
            _line(-1, 9, "PYSEC-2026-1") + _line(-1, 9, "CVE-2026-2"),
            ["--ignore-vuln=PYSEC-2026-1", "--ignore-vuln=CVE-2026-2"],
            id="several",
        ),
    ],
)
def test_current_exceptions_become_ignore_arguments(text: str, expected: list[str]) -> None:
    assert runtime_audit_args.ignore_args(text, TODAY) == expected


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_line(-40, -1), id="expired"),
        pytest.param(_line(-10, 81), id="longer-than-90-days"),
        pytest.param(_line(1, 30), id="added-in-the-future"),
        pytest.param(_line(-1, 30, "ghsa-aaaa"), id="lowercase-advisory-id"),
        pytest.param(_line(-1, 30, "GHSA-a;rm"), id="shell-metacharacter-in-id"),
        pytest.param(_line(-1, 30, "--help"), id="option-instead-of-id"),
        pytest.param(f"{ADVISORY} owner {TODAY} {TODAY + timedelta(30)}\n", id="no-reason"),
        pytest.param(f"{ADVISORY} owner 2026-13-01 2026-12-01 reason\n", id="impossible-date"),
    ],
)
def test_expired_or_malformed_exception_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="line 1"):
        runtime_audit_args.ignore_args(text, TODAY)


def test_rejection_names_the_offending_line() -> None:
    with pytest.raises(ValueError, match="line 3"):
        runtime_audit_args.ignore_args("# c\n" + _line(-1, 9) + _line(-40, -1), TODAY)


@pytest.mark.parametrize(("expires", "code"), [(30, 0), (-1, 1)], ids=["current", "expired"])
def test_command_prints_arguments_and_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], expires: int, code: int
) -> None:
    today = datetime.now(UTC).date()
    exceptions = tmp_path / "exceptions.txt"
    exceptions.write_text(
        f"{ADVISORY} owner {today - timedelta(40)} {today + timedelta(expires)} r\n"
    )

    assert runtime_audit_args.main(str(exceptions)) == code

    out = capsys.readouterr()
    assert out.out == (f"--ignore-vuln={ADVISORY}\n" if code == 0 else "")
    assert ("line 1" in out.err) == (code == 1)


def test_command_fails_when_the_exceptions_file_is_missing(tmp_path: Path) -> None:
    assert runtime_audit_args.main(str(tmp_path / "missing.txt")) == 1
