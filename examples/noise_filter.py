"""Rate-limit a noisy third-party logger on one isolated handler.

Run ``python examples/noise_filter.py``. A synthetic "third-party" logger floods INFO
records; a ``SamplingFilter`` scoped to that logger name keeps the first few and drops
the rest, while

* WARNING and above from the same library always pass (errors are never silenced),
* the application logger is untouched (the filter is scoped by logger name),
* the filter lives on an ``IsolatedHandler`` wrapper, so other handlers on the same
  loggers still receive every record, and
* the root logger and unrelated libraries are never modified.

Everything uses a private logger namespace, a fake library and an in-memory stream.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import sys
from typing import TextIO

from azure_functions_logging import IsolatedHandler, JsonFormatter, SamplingFilter

SCOPE = "examples_noise"  # private namespace that owns the handler
THIRD_PARTY = f"{SCOPE}.thirdparty.http"  # stands in for e.g. "urllib3" or "azure.core"
APP = f"{SCOPE}.app"
RATE = 2  # INFO records kept per window from the noisy library
WINDOW = 3600.0  # long window: deterministic, no timing dependence in tests


def install(stream: TextIO) -> Callable[[], None]:
    """Attach the isolated, sampled handler to the private scope and return an undo."""
    scope = logging.getLogger(SCOPE)
    previous = (scope.level, scope.propagate)

    target = logging.StreamHandler(stream)
    target.setFormatter(JsonFormatter())
    isolated = IsolatedHandler(target)  # filters below run on a cloned record
    isolated.addFilter(SamplingFilter(rate=RATE, window=WINDOW, name=f"{SCOPE}.thirdparty"))

    scope.addHandler(isolated)
    scope.setLevel(logging.INFO)
    scope.propagate = False  # keep the demo records away from the root logger

    def undo() -> None:
        """Remove exactly what ``install`` added; call this in test teardown."""
        scope.removeHandler(isolated)
        scope.setLevel(previous[0])
        scope.propagate = previous[1]

    return undo


def emit_traffic() -> None:
    """Produce noisy third-party records plus application records."""
    noisy = logging.getLogger(THIRD_PARTY)
    for index in range(5):
        noisy.info("connection pool event %d", index)  # sampled: only RATE are kept
    noisy.warning("retrying request")  # always passes
    noisy.error("request failed")  # always passes
    app = logging.getLogger(APP)
    for step in ("received", "validated", "completed"):
        app.info("order %s", step)  # not matched by the filter scope


def main() -> None:
    """Print the surviving records, then undo the setup."""
    undo = install(sys.stdout)
    try:
        emit_traffic()
    finally:
        undo()


if __name__ == "__main__":
    main()
