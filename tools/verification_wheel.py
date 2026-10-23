"""Check installed wheel identity outside the source checkout."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile

from tools.verification_process import run


def main() -> int:
    directory = Path("test-results/wheel-smoke/logs")
    with tempfile.TemporaryDirectory(prefix="logging-wheel-") as temporary:
        root = Path(temporary)
        code = run(
            [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(root / "dist")],
            directory / "build.log",
        )
        if code:
            return code
        wheels = list((root / "dist").glob("*.whl"))
        if len(wheels) != 1:
            print("Expected exactly one freshly built wheel in isolated output directory")
            return 1
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(root / "venv")], check=True
        )
        python = str(root / "venv/bin/python")
        packages = (
            root
            / "venv/lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
        (packages / "verification-dependencies.pth").write_text(
            sysconfig.get_path("purelib") + "\n"
        )
        code = run(
            [python, "-m", "pip", "install", "--no-deps", "--no-index", str(wheels[0].resolve())],
            directory / "wheel-install.log",
        )
        if code:
            return code
        script = (
            "from pathlib import Path; import logging; import azure_functions_logging as a; "
            f"assert Path(a.__file__).resolve().is_relative_to(Path({str(root)!r})); "
            "assert a.get_logger('artifact-smoke').name == 'artifact-smoke'; "
            "record=logging.LogRecord('artifact-smoke',20,'smoke',1,"
            "'installed wheel smoke',(),None); "
            "assert 'installed wheel smoke' in a.JsonFormatter().format(record); "
            "print('Installed wheel imports and formats outside checkout')"
        )
        return run([python, "-I", "-c", script], directory / "wheel-smoke.log")


if __name__ == "__main__":
    raise SystemExit(main())
