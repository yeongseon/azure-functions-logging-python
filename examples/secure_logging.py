"""Opt-in secure logging with fake sensitive values.

Run ``python examples/secure_logging.py`` to see which fields are masked and which
non-sensitive fields stay visible. Everything here is synthetic: the ``canary-*``
strings exist only so a test can prove they are masked. Secure redaction is
**opt-in** and key/pattern based; it is not a promise that every secret is found,
so a secret in plain free text with no recognizable key is not masked.
"""

from __future__ import annotations

import logging

from azure_functions_logging import configure_secure_redaction, get_logger, setup_logging

LOGGER_NAME = "examples.secure_logging"

# Synthetic values, named neutrally so scanners do not mistake them for credentials.
CANARY_A = "canary-token-0000"
CANARY_B = "canary-password-0000"
CANARY_C = "canary-api-key-0000"
CANARY_D = "canary-message-secret-0000"


def main() -> None:
    """Log sensitive and non-sensitive fields with the secure preset enabled."""
    # A named logger keeps the root logger untouched.
    setup_logging(format="json", level=logging.INFO, logger_name=LOGGER_NAME)
    # Opt in AFTER setup so the preset covers the handler that setup just installed.
    configure_secure_redaction()

    logger = get_logger(LOGGER_NAME)

    # Sensitive keys: values are masked, the keys stay visible.
    logger.info(
        "user signed in",
        token=CANARY_A,
        password=CANARY_B,
        api_key=CANARY_C,
    )
    # Deliberately non-sensitive keys are left as-is.
    logger.info("order accepted", order_id="o-123", tenant_id="tenant-a", status="ok")
    # A recognizable ``key=value`` shape inside a message is masked as well.
    logger.info("calling upstream with password=%s", CANARY_D)


if __name__ == "__main__":
    main()
