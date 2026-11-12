"""Call ``setup_logging`` repeatedly without duplicate output or root-logger changes.

Run ``python examples/repeated_setup.py``. A warm Azure Functions worker may run your
startup code more than once (module re-import, several entry points that each call
setup). In standalone local mode with an explicit ``logger_name``:

* the *first* call for a name wins; repeat calls are no-ops, so every message is
  emitted exactly once and the later ``level=`` is ignored,
* the root logger and unrelated libraries keep their own handlers, filters and level,
* a child logger reaches the handler by *inheritance* (``propagate``), which is why it
  also emits once: idempotency covers one logger name, inheritance covers its children.

Azure / Core Tools mode has its own, handler-level idempotency (see the
``setup_logging`` docstring); this example uses the local mode only.
"""

from __future__ import annotations

import logging

from azure_functions_logging import setup_logging

LOGGER_NAME = "examples.repeated_setup"
CHILD_NAME = f"{LOGGER_NAME}.worker"


def configure() -> logging.Logger:
    """Safe to call from every entry point: only the first call has any effect."""
    setup_logging(format="json", level=logging.INFO, logger_name=LOGGER_NAME)
    return logging.getLogger(LOGGER_NAME)


def reconfigure_with_other_level() -> logging.Logger:
    """A later call with a different level is ignored; change it with ``setLevel``."""
    setup_logging(format="json", level=logging.DEBUG, logger_name=LOGGER_NAME)
    return logging.getLogger(LOGGER_NAME)


def main() -> None:
    """Configure three times (the last asks for DEBUG), then log once per logger."""
    configure()
    configure()
    app = reconfigure_with_other_level()
    app.info("emitted once")
    app.debug("not emitted: the first call set INFO")
    logging.getLogger(CHILD_NAME).info("child emits once via inheritance")


def teardown() -> None:
    """Undo for tests: drop what setup installed on this logger (not on any other).

    ``setup_logging`` remembers a configured ``logger_name`` for the life of the process,
    so after this teardown a second ``configure()`` is still a no-op. Give each test its
    own ``logger_name`` (or, as this repository's tests do, clear the package's private
    registry) when a test needs a fresh installation.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.filters.clear()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


if __name__ == "__main__":
    main()
    teardown()
