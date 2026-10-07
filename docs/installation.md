# Installation

Installing `azure-functions-logging` requires Python 3.11-3.14 (`>=3.11,<3.15`). The package has no external runtime dependencies.

## Using pip

Install from PyPI:

```bash
pip install azure-functions-logging
```

To install a specific version, substitute the release you want (see the
[PyPI release history](https://pypi.org/project/azure-functions-logging/#history)):

```bash
pip install azure-functions-logging==X.Y.Z
```

## Adding to Requirements

For Azure Functions projects, add the package to your `requirements.txt` file to ensure it is available in the deployment environment:

```text
# requirements.txt
azure-functions
azure-functions-logging
```

Azure Functions reads `requirements.txt` during deployment and installs the listed packages in the remote environment.

For reproducible deployments, pin an exact release (`azure-functions-logging==X.Y.Z`) and bump it deliberately. The package follows semantic versioning and is pre-1.0, so a minor bump can carry behavior changes.

## Using pyproject.toml

If your project uses `pyproject.toml` for dependency management:

```toml
[project]
dependencies = [
    "azure-functions",
    "azure-functions-logging",
]
```

## Development Installation

To contribute to the project or run tests locally, clone the repository and install in editable mode with development dependencies:

```bash
git clone https://github.com/yeongseon/azure-functions-logging-python.git
cd azure-functions-logging-python
pip install -e ".[dev]"
```

This installs the package in editable mode along with development tools (pytest, mypy, ruff, bandit).

## Prerequisites

- **Python**: >= 3.11 (tested on 3.11, 3.12, 3.13, 3.14)
- **External Dependencies**: None. This package uses only the Python standard library at runtime.
- **Build System**: [Hatch](https://hatch.pypa.io/) (for development and publishing)

## Verifying the Installation

After installation, verify the package is available:

```python
import azure_functions_logging
print(azure_functions_logging.__version__)
# X.Y.Z -- matches the installed distribution
```

Or from the command line:

```bash
python -c "import azure_functions_logging; print(azure_functions_logging.__version__)"
```

## Upgrading

To upgrade to the latest version:

```bash
pip install --upgrade azure-functions-logging
```

## Compatibility Notes

- This package is designed for the Azure Functions Python v2 programming model
- It works in both local development environments and Azure-hosted environments
- The package automatically detects its runtime environment and adjusts behavior accordingly
- While designed for Azure Functions, the logging helpers work in any Python application -- the Azure-specific features (context injection, host.json detection) simply have no effect outside Azure
