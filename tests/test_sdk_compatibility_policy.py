from pathlib import Path
import tomllib

import yaml


def test_wheel_and_host_smokes_select_oldest_and_latest_sdk() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci-test.yml").read_text())
    for name in ("artifact-python311", "host-smoke"):
        job = workflow["jobs"][name]
        assert job["strategy"]["matrix"]["sdk"] == [
            "azure-functions==1.21.0",
            "azure-functions>=1.21.0",
        ]
        steps = job["steps"]
        assert any("matrix.sdk" in step.get("run", "") for step in steps)
    assert "artifact-build" in workflow["jobs"]["host-smoke"]["needs"]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    assert "azure-functions>=1.21.0" in project["project"]["dependencies"]
