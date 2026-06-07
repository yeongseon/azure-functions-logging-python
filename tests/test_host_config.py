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
    # Host.Results is a host-internal category and should NOT warn by default
    assert not any("Host.Results" in m for m in messages)
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


def test_host_internal_category_not_warned_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host-internal categories (Host.*) must not warn in default mode."""
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"Host.Results": "Error", "Host.Aggregator": "Error"}}},
    )
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)
    assert warning_list == [], "Expected no warnings for host-internal categories"


def test_host_internal_category_warned_in_strict_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """strict=True must include host-internal categories."""
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"Host.Results": "Error"}}},
    )
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO, strict=True)
    messages = [str(w.message) for w in warning_list]
    assert any("Host.Results" in m for m in messages)
    nested = tmp_path / "src" / "functions"
    nested.mkdir(parents=True)
    _write_host_json(
        tmp_path / "host.json",
        {"logging": {"logLevel": {"default": "Warning"}}},
    )
    monkeypatch.chdir(nested)
    with pytest.warns(UserWarning, match="more restrictive"):
        warn_host_json_level_conflict(logging.INFO)


# ---------------------------------------------------------------------------
# discover_host_json — AzureWebJobsScriptRoot env var (issue #163)
# ---------------------------------------------------------------------------


def test_discover_uses_azurewebjobsscriptroot_when_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When AzureWebJobsScriptRoot is set, discover_host_json prefers that directory."""
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.setenv("AzureWebJobsScriptRoot", str(tmp_path))
    # cwd is a different dir that has no host.json
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)

    found = discover_host_json()
    assert found == (tmp_path / "host.json").resolve()


def test_discover_falls_through_when_azurewebjobsscriptroot_has_no_host_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var set but no host.json inside — falls back to cwd walk."""
    env_dir = tmp_path / "func_root"
    env_dir.mkdir()
    # no host.json in env_dir
    monkeypatch.setenv("AzureWebJobsScriptRoot", str(env_dir))

    # cwd has host.json via parent walk
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(cwd)

    found = discover_host_json()
    assert found == (tmp_path / "host.json").resolve()


def test_discover_falls_through_when_azurewebjobsscriptroot_path_does_not_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var set to a non-existent directory — falls back to cwd walk."""
    monkeypatch.setenv("AzureWebJobsScriptRoot", "/nonexistent/path/that/does/not/exist")

    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(tmp_path)

    found = discover_host_json()
    assert found == (tmp_path / "host.json").resolve()


def test_discover_explicit_start_ignores_azurewebjobsscriptroot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit start param takes priority over AzureWebJobsScriptRoot env var."""
    env_dir = tmp_path / "env_root"
    env_dir.mkdir()
    _write_host_json(env_dir / "host.json", {"version": "env"})
    monkeypatch.setenv("AzureWebJobsScriptRoot", str(env_dir))

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    _write_host_json(explicit_dir / "host.json", {"version": "explicit"})

    found = discover_host_json(start=explicit_dir)
    assert found == (explicit_dir / "host.json").resolve()
    # confirm the env dir's host.json was NOT returned
    assert found != (env_dir / "host.json").resolve()


def test_discover_falls_through_when_env_root_resolve_raises_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RuntimeError (e.g. symlink loop) from Path.resolve() is swallowed; cwd walk used."""
    monkeypatch.setenv("AzureWebJobsScriptRoot", "/some/path")
    _write_host_json(tmp_path / "host.json", {"version": "2.0"})
    monkeypatch.chdir(tmp_path)

    original_resolve = Path.resolve

    def _raise_on_some_path(self: Path, *, strict: bool = False) -> Path:
        if str(self) == "/some/path":
            raise RuntimeError("Too many levels of symbolic links")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", _raise_on_some_path)

    # Must not raise; must fall back to cwd walk and find tmp_path/host.json
    found = discover_host_json()
    assert found == (tmp_path / "host.json").resolve()


# ---------------------------------------------------------------------------
# AzureFunctionsJobHost app setting logLevel overrides (issue #171)
# ---------------------------------------------------------------------------


def test_warns_when_app_setting_override_sets_default_more_restrictive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AzureFunctionsJobHost__logging__logLevel__default",
        "Warning",
    )

    with pytest.warns(UserWarning, match="more restrictive") as warning_list:
        warn_host_json_level_conflict(logging.INFO)

    message = str(warning_list[0].message)
    assert "AzureFunctionsJobHost app setting" in message
    assert "default" in message
    assert "'Warning'" in message
    assert "'INFO'" in message


def test_warns_when_app_setting_override_sets_function_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AzureFunctionsJobHost__logging__logLevel__Function__MyFunction",
        "Error",
    )

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    messages = [str(w.message) for w in warning_list]
    assert any("Function.MyFunction" in message and "'Error'" in message for message in messages)


def test_app_setting_override_ignores_host_internal_categories_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AzureFunctionsJobHost__logging__logLevel__Host__Results",
        "Error",
    )

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


def test_app_setting_override_warns_for_host_internal_categories_in_strict_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AzureFunctionsJobHost__logging__logLevel__Host__Results",
        "Error",
    )

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO, strict=True)

    messages = [str(w.message) for w in warning_list]
    assert any("Host.Results" in message for message in messages)


def test_app_setting_override_ignores_unrecognized_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AzureFunctionsJobHost__logging__logLevel__default",
        "SuperVerbose",
    )

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always")
        warn_host_json_level_conflict(logging.INFO)

    assert len(warning_list) == 0


def test_app_setting_override_is_checked_even_when_host_json_is_malformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "host.json").write_text("not valid json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AzureFunctionsJobHost__logging__logLevel__default",
        "Warning",
    )

    with pytest.warns(UserWarning, match="AzureFunctionsJobHost app setting"):
        warn_host_json_level_conflict(logging.INFO)
