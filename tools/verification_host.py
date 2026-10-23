"""Real logging host smokes with private Azurite storage and owned processes."""

from __future__ import annotations

import base64
from contextlib import ExitStack
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from scripts.assert_correlation import check
from tools.verification_process import child


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(process: subprocess.Popen[str], url: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("service exited before readiness")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError, HTTPException):
            time.sleep(0.25)
    raise TimeoutError("service readiness deadline exceeded")


def assert_routes(base: str, matrix: bool, work: Path) -> str:
    if not matrix:
        for route, expected in (("smoke", "smoke"), ("smoke-default", "smoke_default")):
            with urlopen(f"{base}/{route}", timeout=5) as response:
                assert response.read().decode() == expected
        return ""
    with urlopen(f"{base}/health", timeout=5) as response:
        assert json.load(response)["status"] == "ok"
    with urlopen(f"{base}/version", timeout=5) as response:
        assert json.load(response)["version"]
    with urlopen(f"{base}/correlation", timeout=5) as response:
        text: str = response.read().decode()
    (work / "correlation-response.json").write_text(text)
    return text


def host_smoke(directory: Path, matrix: bool = False) -> int:
    directory = directory.resolve()
    suite = ET.Element("testsuite", name="real-functions-host")
    case = ET.SubElement(suite, "testcase", name="correlation" if matrix else "decorated_handlers")
    try:
        with tempfile.TemporaryDirectory(prefix="logging-host-") as temporary, ExitStack() as stack:
            work = Path(temporary)
            source = Path("examples/e2e_app" if matrix else "tests/host_smoke")
            for name in ("function_app.py", "host.json"):
                (work / name).write_bytes((source / name).read_bytes())
            ports: set[int] = set()
            while len(ports) < 4:
                ports.add(free_port())
            blob, queue, table, port = ports
            key = base64.b64encode(b"logging-local-emulator-only" * 2).decode()
            emulator = stack.enter_context(
                child(
                    [
                        "env",
                        f"AZURITE_ACCOUNTS=loggingdev:{key}",
                        "azurite",
                        "--silent",
                        "--location",
                        str(work / "storage"),
                        "--blobPort",
                        str(blob),
                        "--queuePort",
                        str(queue),
                        "--tablePort",
                        str(table),
                    ],
                    directory / "logs/azurite.log",
                )
            )
            deadline = time.monotonic() + 30
            for service in (blob, queue, table):
                while True:
                    if emulator.poll() is not None or time.monotonic() >= deadline:
                        raise TimeoutError("Azurite failed readiness")
                    try:
                        with socket.create_connection(("127.0.0.1", service), timeout=1):
                            break
                    except OSError:
                        time.sleep(0.25)
            (work / "local.settings.json").write_text(
                json.dumps(
                    {
                        "IsEncrypted": False,
                        "Values": {
                            "FUNCTIONS_WORKER_RUNTIME": "python",
                            "AzureWebJobsStorage": (
                                f"DefaultEndpointsProtocol=http;AccountName=loggingdev;AccountKey={key};"
                                f"BlobEndpoint=http://127.0.0.1:{blob}/loggingdev;"
                                f"QueueEndpoint=http://127.0.0.1:{queue}/loggingdev;"
                                f"TableEndpoint=http://127.0.0.1:{table}/loggingdev;"
                            ),
                        },
                    }
                )
            )
            previous_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + previous_path
            try:
                host = stack.enter_context(
                    child(
                        ["func", "start", "--python", "--verbose", "--port", str(port)],
                        directory / "logs/host.log",
                        work,
                    )
                )
                base = f"http://127.0.0.1:{port}/api"
                wait_ready(host, base + ("/health" if matrix else "/smoke"))
                text = assert_routes(base, matrix, directory)
            finally:
                os.environ["PATH"] = previous_path
        host_text = (directory / "logs/host.log").read_text()
        assert not re.search(
            r"0 functions (loaded|found \(Worker\))|No job functions found|"
            r"Executed 'Functions\..*' \(Failed",
            host_text,
        )
        if matrix:
            failures = check(host_text, text)
            assert not failures, "; ".join(failures)
        code = 0
    except (OSError, RuntimeError, TimeoutError, AssertionError, ValueError) as error:
        ET.SubElement(case, "failure").text = str(error)
        code = 1
    finally:
        destination = directory / "junit/junit.xml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(suite).write(destination, encoding="unicode")
    return code
