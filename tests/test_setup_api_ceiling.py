"""Secure configuration must not expand the setup keyword matrix."""

import inspect

from azure_functions_logging import setup_logging


def test_setup_preserves_eight_keyword_contract() -> None:
    # Given / When: inspect the public setup entry point.
    parameters = inspect.signature(setup_logging).parameters.values()
    # Then: privacy configuration does not add a ninth setup keyword.
    assert sum(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters) == 8
