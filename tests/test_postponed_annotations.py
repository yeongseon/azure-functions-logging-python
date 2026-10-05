from __future__ import annotations

from collections.abc import Iterator
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import get_type_hints

import azure.functions as func
import pytest


@pytest.fixture(params=[False, True], ids=["eager", "postponed"])
def handler_module_with_none_default(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[ModuleType]:
    postponed = request.param
    module_name = f"none_default_handlers_{'postponed' if postponed else 'eager'}"
    module_path = tmp_path / f"{module_name}.py"
    future_import = "from __future__ import annotations\n\n" if postponed else ""
    module_path.write_text(
        f"""{future_import}import azure.functions as func
from azure_functions_logging import with_context

@with_context(strict=True)
def handler(
    req: func.HttpRequest, context: func.Context = None
) -> func.HttpResponse:
    return func.HttpResponse("ok")
""",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.fixture
def postponed_handler_module(tmp_path: Path) -> Iterator[ModuleType]:
    module_path = tmp_path / "postponed_handlers.py"
    module_path.write_text(
        """from __future__ import annotations

import azure.functions as func
from azure_functions_logging import with_context

app = func.FunctionApp()

@app.route(route="indexed")
@with_context(strict=True)
def indexed(
    req: func.HttpRequest, context: func.Context
) -> func.HttpResponse:
    return func.HttpResponse("ok")

@with_context(strict=True)
def strict_sync(
    req: func.HttpRequest, context: func.Context
) -> func.HttpResponse:
    return func.HttpResponse("ok")

@with_context()
def non_strict_sync(
    req: func.HttpRequest, context: func.Context
) -> func.HttpResponse:
    return func.HttpResponse("ok")

@with_context(strict=True)
async def strict_async(
    req: func.HttpRequest, context: func.Context
) -> func.HttpResponse:
    return func.HttpResponse("ok")

@with_context()
async def non_strict_async(
    req: func.HttpRequest, context: func.Context
) -> func.HttpResponse:
    return func.HttpResponse("ok")
""",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("postponed_handlers", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_preserves_concrete_context_annotation_with_none_default(
    handler_module_with_none_default: ModuleType,
) -> None:
    # Given a separately imported handler with a concrete Context annotation
    handler = handler_module_with_none_default.handler

    # When @with_context copies the handler metadata
    context_annotation = handler.__annotations__["context"]

    # Then the worker sees Context rather than an implicit Optional[Context]
    assert context_annotation is func.Context


@pytest.mark.parametrize(
    "handler_name",
    ["strict_sync", "non_strict_sync", "strict_async", "non_strict_async"],
)
def test_resolves_postponed_annotations_from_handler_module(
    postponed_handler_module: ModuleType,
    handler_name: str,
) -> None:
    # Given a separately imported handler whose annotations use its local alias
    handler = getattr(postponed_handler_module, handler_name)

    # When the worker resolves the decorated callable's type hints
    hints = get_type_hints(handler)

    # Then every annotation is a concrete Azure Functions type
    assert hints == {
        "req": func.HttpRequest,
        "context": func.Context,
        "return": func.HttpResponse,
    }


def test_worker_indexes_handler_with_postponed_annotations(
    postponed_handler_module: ModuleType,
) -> None:
    worker_functions = pytest.importorskip("azure_functions_worker.functions")
    app = postponed_handler_module.app
    indexed_function = app.get_functions()[0]

    function_info = worker_functions.Registry().add_indexed_function(indexed_function)

    assert function_info.requires_context is True
