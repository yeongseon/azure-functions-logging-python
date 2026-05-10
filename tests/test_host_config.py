from __future__ import annotations

import json
import logging
from pathlib import Path
import warnings

import pytest

from azure_functions_logging._host_config import discover_host_json, warn_host_json_level_conflict


def _write_host_json(path: Path, content: dict[str, object]) -> None:
    path.write_text(json.dumps(content), encoding="utf-8")


def test_warns_when_host_level_is_more_restrictive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": "Warning"}}},
    )
    monkeypatch.chdir(tmp_path)

    with pytest.warns(UserWarning, match="more restrictive") as warning_list:
        warn_host_json_level_conflict(logging.INFO)

    message = str(warning_list[0].message)
    assert "'Warning'" in message
    assert "'INFO'" in message


def test_no_warning_when_host_level_is_less_restrictive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": "Information"}}},
    )
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.WARNING)

    assert len(warning_list) == 0


def test_no_warning_when_host_json_does_not_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


def test_no_warning_when_logging_config_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


def test_warns_when_host_level_is_none_disables_all_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """logLevel.default = 'None' disables all logging — should always warn."""
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": "None"}}},
    )
    monkeypatch.chdir(tmp_path)

    with pytest.warns(UserWarning, match="more restrictive") as warning_list:
        warn_host_json_level_conflict(logging.DEBUG)

    message = str(warning_list[0].message)
    assert "'None'" in message


def test_no_warning_when_host_json_is_malformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines 29-30: invalid JSON in host.json is silently ignored."""
    (tmp_path / "host.json").write_text("not valid json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


def test_no_warning_when_log_level_value_is_not_a_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 38: logLevel.default is not a str (e.g. an integer) -> silently ignored."""
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": 42}}},
    )
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.DEBUG)

    assert len(warning_list) == 0


def test_no_warning_when_host_level_is_unrecognized_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 42: logLevel.default is a string not in _HOST_LEVEL_TO_LOGGING -> silently ignored."""
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": "SuperVerbose"}}},
    )
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.DEBUG)

    assert len(warning_list) == 0


def test_warns_per_category_when_specific_category_is_more_restrictive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(
        tmp_path / "host.json",
        {
            "logging": {
                "logLevel": {
                    "default": "Information",
                    "Function.MyFunction": "Warning",
                    "Host.Results": "Error",
                }
            }
        },
    )
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    messages = [str(w.message) for w in warning_list]
    assert any("Function.MyFunction" in m and "'Warning'" in m for m in messages)
    assert any("Host.Results" in m and "'Error'" in m for m in messages)
    assert not any("default" in m for m in messages)


def test_no_warning_when_all_categories_permissive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(
        tmp_path / "host.json",
        {
            "logging": {
                "logLevel": {
                    "default": "Information",
                    "Function": "Debug",
                    "Host.Aggregator": "Trace",
                }
            }
        },
    )
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


def test_no_warning_when_log_level_block_is_not_a_dict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": "Warning"}},
    )
    monkeypatch.chdir(tmp_path)

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


# ---------------------------------------------------------------------------
# Discovery + override tests (issue #102)
# ---------------------------------------------------------------------------


def test_discover_host_json_finds_in_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(tmp_path)
    found = discover_host_json()
    assert found == (tmp_path / "host.json").resolve()


def test_discover_host_json_walks_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(nested)
    found = discover_host_json()
    assert found == (tmp_path / "host.json").resolve()


def test_discover_host_json_returns_none_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert discover_host_json() is None


def test_discover_host_json_respects_max_depth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 7 nested levels — host.json placed at the very top, beyond the bounded walk.
    deep = tmp_path
    for name in ("a", "b", "c", "d", "e", "f", "g"):
        deep = deep / name
    deep.mkdir(parents=True)
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(deep)
    assert discover_host_json() is None


def test_discover_host_json_picks_nearest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "app"
    nested.mkdir()
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    _write_host_json(nested / "host.json", {"version": "4.0"})
    monkeypatch.chdir(nested)
    found = discover_host_json()
    assert found == (nested / "host.json").resolve()


def test_warn_uses_explicit_override_when_cwd_has_no_host_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    _write_host_json(
        other / "host.json",
        {"logging": {"logLevel": {"default": "Warning"}}},
    )
    # cwd has no host.json — discovery would yield nothing.
    monkeypatch.chdir(tmp_path)
    with pytest.warns(UserWarning, match="more restrictive"):
        warn_host_json_level_conflict(
            logging.INFO,
            host_json_path=other / "host.json",
        )


def test_warn_override_missing_file_silently_skipped(
    tmp_path: Path,
) -> None:
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(
            logging.INFO,
            host_json_path=tmp_path / "does-not-exist.json",
        )
    assert len(warning_list) == 0


def test_warn_walks_parents_to_find_host_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-discovery must reach host.json even when cwd is a subdirectory."""
    nested = tmp_path / "src" / "functions"
    nested.mkdir(parents=True)
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": "Warning"}}},
    )
    monkeypatch.chdir(nested)
    with pytest.warns(UserWarning, match="more restrictive"):
        warn_host_json_level_conflict(logging.INFO)
