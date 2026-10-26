VENV_DIR := .venv
PIP := $(VENV_DIR)/bin/pip
HATCH := $(VENV_DIR)/bin/hatch

# Created once; routine targets never upgrade pip or reinstall Hatch. Hatch counts as installed
# only if it is an executable regular file: `-x` alone is also true for a searchable directory.
.PHONY: bootstrap
bootstrap:
	@test -d "$(VENV_DIR)" || { echo "Creating virtual environment..."; python3 -m venv "$(VENV_DIR)"; }
	@{ [ -f "$(HATCH)" ] && [ -x "$(HATCH)" ]; } || { echo "Installing Hatch..."; "$(PIP)" install hatch > /dev/null; }

.PHONY: ensure-hatch
ensure-hatch: bootstrap

.PHONY: install
install: ensure-hatch
	@$(HATCH) env create
	@if [ -n "$$CI" ]; then \
		echo "CI detected: skipping pre-commit hook installation"; \
	else \
		$(MAKE) precommit-install; \
	fi

.PHONY: shell
shell: ensure-hatch
	@$(HATCH) shell

.PHONY: reset
reset: clean-all install
	@echo "Project reset complete."

.PHONY: hatch-clean
hatch-clean: ensure-hatch
	@$(HATCH) env remove || echo "No hatch environment to remove"

.PHONY: format
format: ensure-hatch
	@$(HATCH) run format

.PHONY: format-check
format-check: ensure-hatch
	@$(HATCH) run format-check

.PHONY: format-check-changed
format-check-changed: ensure-hatch
	@$(HATCH) run python tools/check_pr_format.py "$(BASE)" "$(HEAD)"

.PHONY: style
style: ensure-hatch
	@$(HATCH) run style

.PHONY: typecheck
typecheck: ensure-hatch
	@$(HATCH) run typecheck

.PHONY: lint
lint: ensure-hatch
	@$(HATCH) run lint

# Bandit exits 0 for an empty, missing or unparsable scope; the guard rejects those.
# -q: Bandit 1.9.4 prints a progress bar to stdout above 50 files.
SECURITY_SCOPE := src examples scripts tools benchmarks
.PHONY: security
security: ensure-hatch
	@mkdir -p test-results
	@$(HATCH) run python -m bandit -r $(SECURITY_SCOPE) -q -f json -o test-results/bandit.json; \
	  code=$$?; $(HATCH) run python tools/check_bandit_report.py test-results/bandit.json $(SECURITY_SCOPE) && exit $$code

# `lint` is style + typecheck (see pyproject.toml); a separate `typecheck` here would run mypy twice.
.PHONY: check
check: lint
	@echo "Lint and type check passed."

.PHONY: lint-workflows
lint-workflows: ensure-hatch
	@$(HATCH) run python tools/lint_release_workflows.py
	@$(HATCH) run python tools/lint_workflow_pins.py
	@$(HATCH) run python tools/lint_hatch_matrix.py

.PHONY: lint-doc-links
lint-doc-links: ensure-hatch
	@$(HATCH) run python tools/lint_doc_links.py

.PHONY: check-all
check-all: ensure-hatch
	@$(MAKE) lint-workflows
	@$(MAKE) lint-doc-links
	@$(MAKE) check
	@$(MAKE) test
	@$(MAKE) security
	@echo "All checks passed including tests and security scan."

.PHONY: precommit
precommit: ensure-hatch
	@$(HATCH) run precommit

.PHONY: precommit-install
precommit-install: ensure-hatch
	@$(HATCH) run precommit-install

.PHONY: test
test: ensure-hatch
	@echo "Running tests..."
	@$(HATCH) run test

.PHONY: bench
bench: ensure-hatch
	@echo "Running micro-benchmarks..."
	@$(HATCH) run python benchmarks/bench.py

.PHONY: cov
cov: ensure-hatch
	@$(HATCH) run cov
	@echo "Open htmlcov/index.html in your browser to view the coverage report."
	@echo "coverage.xml generated for Codecov upload."

.PHONY: e2e-local
e2e-local: ensure-hatch
	@echo "Running e2e tests against local Azurite (E2E_BASE_URL=http://localhost:7071)..."
	@echo "E2E_EXPECTED_VERSION defaults to the locally installed candidate version (hatch version); override to certify a different deployed build."
	@E2E_BASE_URL=http://localhost:7071 E2E_EXPECTED_VERSION=$${E2E_EXPECTED_VERSION:-$$($(HATCH) version)} $(HATCH) run e2e-azure

.PHONY: e2e-azure
e2e-azure: ensure-hatch
	@echo "Running e2e tests against Azure (E2E_BASE_URL and E2E_EXPECTED_VERSION must both be set)..."
	@$(HATCH) run e2e-azure

.PHONY: build
build: ensure-hatch
	@$(HATCH) build

.PHONY: publish-test
publish-test: ensure-hatch
	@$(HATCH) publish --repo test

.PHONY: version
version: ensure-hatch
	@echo "Current version:"
	@$(HATCH) version

.PHONY: docs
docs:
	@if [ -n "$$CI" ]; then \
		echo "CI detected: running MkDocs directly"; \
		pip install "mkdocs<2.0" "mkdocs-material<10.0" "mkdocstrings[python]<1.0" > /dev/null 2>&1; \
		mkdocs build; \
	else \
		$(MAKE) ensure-hatch > /dev/null; \
		$(HATCH) run mkdocs build; \
	fi

.PHONY: docs-serve
docs-serve: ensure-hatch
	@$(HATCH) run docs

# Read-only: reports what the targets launch and exits non-zero when a required tool is missing.
# `func` and `azurite` are needed only to run the local Functions host that `make e2e-local` calls.
.PHONY: doctor
doctor:
	@missing=0; \
	have() { p="$$(command -v "$$1")"; [ -f "$$p" ] && [ -x "$$p" ]; }; \
	for tool in "$(HATCH)" python3 git; do \
		if have "$$tool"; then echo "ok       $$tool"; \
		else echo "MISSING  $$tool (required)"; missing=1; fi; \
	done; \
	for tool in func azurite; do \
		if have "$$tool"; then echo "ok       $$tool"; \
		else echo "missing  $$tool (optional: only to run a local Functions host)"; fi; \
	done; \
	exit $$missing

.PHONY: clean
clean:
	@rm -rf *.egg-info dist build __pycache__ .pytest_cache

.PHONY: clean-all
clean-all: clean
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
	@rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage coverage.xml htmlcov .DS_Store $(VENV_DIR) site

.PHONY: help
help:
	@echo "Available commands:" && \
	grep -E '^\.PHONY: ' Makefile | cut -d ':' -f2 | xargs -n1 echo "  - make"
