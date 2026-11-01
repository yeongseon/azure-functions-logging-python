from pathlib import Path
import tomllib

from packaging.requirements import Requirement
import yaml

LATEST_SDK = "azure-functions>=1.21.0,<2.0.0"


def test_wheel_and_host_smokes_select_oldest_and_latest_sdk() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci-test.yml").read_text())
    for name in ("artifact-python311", "host-smoke"):
        job = workflow["jobs"][name]
        assert job["strategy"]["matrix"]["sdk"] == [
            "azure-functions==1.21.0",
            LATEST_SDK,
        ]
        steps = job["steps"]
        assert any("matrix.sdk" in step.get("run", "") for step in steps)
    assert "artifact-build" in workflow["jobs"]["host-smoke"]["needs"]


def test_dependency_markers_split_1x_and_2x_by_interpreter() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    reqs = [
        Requirement(dep)
        for dep in project["project"]["dependencies"]
        if dep.startswith("azure-functions")
    ]
    assert len(reqs) == 2
    assert all(req.marker is not None for req in reqs)

    def active(python_version: str) -> Requirement:
        matches = []
        for req in reqs:
            marker = req.marker
            assert marker is not None
            if marker.evaluate({"python_version": python_version}):
                matches.append(req)
        assert len(matches) == 1, matches
        return matches[0]

    assert str(active("3.11").specifier) == "<2.0.0,>=1.21.0"
    assert str(active("3.12").specifier) == "<2.0.0,>=1.21.0"
    assert str(active("3.13").specifier) == "<3.0.0,>=1.21.0"
    assert str(active("3.14").specifier) == "<3.0.0,>=1.21.0"
    assert not active("3.11").specifier.contains("2.0.0")
    assert not active("3.12").specifier.contains("2.0.0")
    assert active("3.13").specifier.contains("2.0.0")
    assert active("3.14").specifier.contains("2.0.0")
    assert all(not req.specifier.contains("3.0.0") for req in reqs)
