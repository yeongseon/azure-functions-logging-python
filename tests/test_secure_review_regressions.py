"""Protected sink regressions for explicitly labelled synthetic credentials."""

from io import StringIO
import logging
from types import SimpleNamespace

import pytest

from azure_functions_logging import JsonFormatter, attach_secure_redaction

CANARY = "SYNTHETIC_REVIEW_CREDENTIAL"


@pytest.mark.parametrize(
    "record",
    [
        {"msg": "Authorization: Basic %s", "args": (CANARY,)},
        {"msg": "request=%s", "args": ({"token": CANARY},)},
        {"msg": "ordinary", "name": f"token={CANARY}"},
        {"msg": "ordinary", "threadName": f"token={CANARY}"},
        {"msg": "ordinary", "payload": SimpleNamespace(password=CANARY)},
        {"msg": "ordinary", "exc_info": (ValueError, ValueError({"password": CANARY}), None)},
        {
            "msg": "ordinary",
            "exc_info": (ValueError, ValueError(f"Authorization: Basic {CANARY}"), None),
        },
    ],
    ids=[
        "basic",
        "mapping-argument",
        "logger",
        "thread",
        "opaque-extra",
        "exception-mapping",
        "exception-basic",
    ],
)
def test_secure_handler_masks_labelled_credentials(record: dict[str, object]) -> None:
    """Credential labels must remain protected through actual handler formatting."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(
            "%(name)s %(threadName)s %(message)s %(payload)s", defaults={"payload": ""}
        )
    )
    attach_secure_redaction(handler)
    log_record = logging.makeLogRecord(record)

    handler.handle(log_record)

    assert CANARY not in stream.getvalue()
    assert CANARY not in JsonFormatter().format(log_record)


@pytest.mark.parametrize(
    ("message", "arguments", "expected"),
    [
        ("count=%d ratio=%.1f", (42, 1.5), "count=42 ratio=1.5"),
        ("count=%(count)d", {"count": 42}, "count=42"),
    ],
)
def test_secure_handler_preserves_numeric_interpolation(
    message: str, arguments: tuple[int, float] | dict[str, int], expected: str
) -> None:
    """Sanitizing formatting arguments must preserve non-sensitive numeric types."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    attach_secure_redaction(handler)
    record = logging.makeLogRecord({"msg": message, "args": arguments})

    handler.handle(record)

    assert stream.getvalue().strip() == expected
