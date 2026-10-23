VENV_DIR := .venv
PYTHON ?= python
HATCH ?= hatch
ifeq ($(CI),)
RUN := $(HATCH) run python
else
RUN := $(PYTHON)
endif
TREES := src tests tools examples benchmarks scripts
MAINTENANCE_PYTHON = $(shell sh tools/maintenance_python.sh)

.PHONY: bootstrap ensure-hatch install install-ci
bootstrap ensure-hatch:
	@command -v $(HATCH) >/dev/null || { echo "Install Hatch in an isolated tool environment first"; exit 1; }
install: ensure-hatch
	@$(HATCH) env create
	@if [ -z "$$CI" ]; then $(MAKE) precommit-install; fi
install-ci:
	@$(PYTHON) -c 'import sys; assert (3, 11) <= sys.version_info[:2] < (3, 15), sys.version'
	@$(PYTHON) -m pip install -e ".[dev,docs]"

.PHONY: shell reset hatch-clean
shell: ensure-hatch
	@$(HATCH) shell
reset: clean-all install
hatch-clean: ensure-hatch
	@$(HATCH) env remove

.PHONY: format format-check format-check-changed style typecheck lint security
format:
	@$(RUN) -m ruff format $(TREES)
format-check:
	@$(RUN) -m ruff format --check $(TREES)
format-check-changed:
	@$(RUN) tools/check_pr_format.py "$(BASE)" "$(HEAD)"
style: format-check
	@$(RUN) -m ruff check $(TREES)
typecheck:
	@$(RUN) -m mypy src tests tools/verification*.py
lint: style typecheck
security:
	@$(RUN) -m bandit -r src

.PHONY: check lint-workflows lint-doc-links lint-mermaid check-all
lint-workflows:
	@$(RUN) tools/lint_release_workflows.py
	@$(RUN) tools/lint_workflow_pins.py
	@$(RUN) tools/lint_hatch_matrix.py
lint-doc-links:
	@$(RUN) tools/lint_doc_links.py
lint-mermaid:
	@$(RUN) scripts/render_mermaid.py
check:
	@$(RUN) -m tools.verification focused check -m tools.verification_check
.PHONY: check-steps
check-steps: style typecheck security lint-workflows lint-doc-links lint-mermaid
check-all: verify

.PHONY: test integration otel host-smoke host-matrix verify report wheel-smoke
test integration otel host-smoke host-matrix verify:
	@$(RUN) -m tools.verification $@
report:
	@$(MAINTENANCE_PYTHON) -m tools.verification report
wheel-smoke:
	@$(RUN) -m tools.verification focused wheel-smoke -m tools.verification_wheel

.PHONY: cov bench e2e-local e2e-azure build docs docs-serve
cov:
	@$(RUN) -m tools.verification test --cov-report=html
bench:
	@$(RUN) benchmarks/bench.py
e2e-local:
	@E2E_BASE_URL=$${E2E_BASE_URL:-http://localhost:7071} E2E_EXPECTED_VERSION=$${E2E_EXPECTED_VERSION:-$$($(HATCH) version)} $(RUN) -m tools.verification local-e2e
e2e-azure:
	@$(RUN) -m tools.verification azure-e2e
build:
	@$(RUN) -m tools.verification focused build -m build --no-isolation
docs:
	@$(RUN) -m tools.verification focused docs -m mkdocs build --strict
docs-serve:
	@$(RUN) -m mkdocs serve

.PHONY: precommit precommit-install publish-test version
precommit: ensure-hatch
	@$(HATCH) run precommit
precommit-install: ensure-hatch
	@$(HATCH) run precommit-install
publish-test: ensure-hatch
	@$(HATCH) publish --repo test
version: ensure-hatch
	@$(HATCH) version

.PHONY: doctor clean clean-all help
doctor:
	@$(MAINTENANCE_PYTHON) -m tools.verification doctor
clean:
	@$(MAINTENANCE_PYTHON) -m tools.verification clean
clean-all: clean
	@find . -type d -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} +
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -not -path "./.git/*" -delete
	@rm -rf .DS_Store $(VENV_DIR)
help:
	@echo "Canonical: install install-ci doctor format format-check check test integration verify e2e-azure report clean"
	@echo "check-all: exact alias of verify (requires func and Azurite)"
	@echo "Partial/focused: style lint typecheck security lint-workflows lint-doc-links cov bench otel host-smoke host-matrix build wheel-smoke docs docs-serve format-check-changed"
	@echo "Local only, not Azure certification: e2e-local"
	@echo "Maintenance: bootstrap ensure-hatch shell reset hatch-clean clean-all precommit precommit-install publish-test version"
