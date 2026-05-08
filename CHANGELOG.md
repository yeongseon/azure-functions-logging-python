# Changelog

All notable changes to this project will be documented in this file.

### Bug Fixes

- *(logger)* Correct merge precedence to bind < extra < kwargs 

### Miscellaneous Tasks

- Bump version to 0.7.1 

### Refactor

- *(logger)* Prevent silent overwrite in _sanitize_extra() on rename collision 

### Testing

- *(logger)* Add regression tests for control kwarg leakage and sanitize double-prefix 

### Bug Fixes

- Address PR #94 review — marker-based idempotency, extra collision safety, tests 
- Address PR review — CI fix, docstrings, ContextTokens alias, README, single-use test 
- Address PR review — mypy attr-defined, README accuracy, filter docstrings 
- V0.5.4 — correct README examples, warn on ignored format in Azure, honor filter name semantics 

### Documentation

- Update changelog 
- Unify README examples around logging_context() as primary pattern 
- Update README — add install_context_factory section, fix AI guidance examples 
- Final cleanup — README wording, test dedup, trace_id nested restore 
- Fix ecosystem table names, badges, and Part of intro line 
- Mark cookbook as dogfood, fix ecosystem table description 
- Replace non-existent python-dx link with cookbook repo 
- Fix cross-repo links and README title 
- *(agents)* Add Issue Conventions section to AGENTS.md 

### Features

- V0.7.0 — add install_context_factory() for global LogRecord context injection 
- V0.6.0 — token-based context restore for safe nested logging_context() 

### Miscellaneous Tasks

- Soften idempotency docstring, move test imports to top-level 
- *(deps)* Bump github/codeql-action from 4.35.2 to 4.35.3 

### Testing

- Raise coverage to 95%+ and enforce via AGENTS.md and pyproject.toml 

### Documentation

- Update changelog 
- Clarify Application Insights ingestion, cold_start semantics, and KQL shapes (#85) 

### Features

- *(context)* Add reset_context/logging_context and category-aware host.json warnings (#84) 

### Miscellaneous Tasks

- *(deps)* Bump softprops/action-gh-release from 2.6.1 to 3.0.0 (#72) 
- *(deps)* Bump github/codeql-action from 4.35.1 to 4.35.2 (#71) 
- *(deps)* Bump ruff from 0.15.10 to 0.15.12 (#75) 
- *(deps)* Bump mypy from 1.20.0 to 1.20.2 (#76) 

### Other

- Bump version to 0.5.3 

### Testing

- Bump expected __version__ to 0.5.3 ahead of release-patch 

### Bug Fixes

- Release pipeline + correctness hotfixes (#77) (#80) 

### Documentation

- Update changelog 
- Add Request Flow and Runtime Relationship section to architecture 

### Miscellaneous Tasks

- *(deps)* Bump actions/github-script from 8.0.0 to 9.0.0 
- *(deps)* Bump actions/upload-artifact from 7.0.0 to 7.0.1 

### Bug Fixes

- Rewrite design principle per Oracle review 
- Switch Mermaid fence format to fence_div_format for rendering 
- Make setup_logging idempotent per logger_name (#34) 
- Prevent RedactionFilter crashes on attribute access errors (#33) 
- Add threading lock and mark-on-success for setup_logging 
- Make setup_logging idempotent per logger name 

### Documentation

- Update changelog 
- Apply Oracle review fixes to Before/After section (#65) 
- Add ecosystem table to README 
- Add llms.txt for LLM-friendly documentation (#56) (#57) 
- Normalize storage naming rule to use en-dash (3–24) 
- Rewrite deployment guide for developer-friendly Azure Functions experience 
- Add Azure deployment verification note to README (#52) 
- Add Azure-verified sample output to README (#51) 
- Add deployment guide with structured logging verification (#49) 
- Add ecosystem positioning and design principle 
- Enable Mermaid diagram rendering on GitHub Pages 
- Add Key Design Decisions and fix idempotency wording (#42) 
- Standardize architecture docs with Mermaid diagrams, Sources, See Also 
- Add release process to AGENTS.md 

### Features

- Add toolkit metadata convention support 

### Miscellaneous Tasks

- Add cliff.toml and bump ruff to 0.15.10 (#62) 
- Add CODE_OF_CONDUCT.md and SUPPORT.md for DX Toolkit consistency (#60) 
- *(deps)* Bump softprops/action-gh-release from 2.2.2 to 2.6.1 
- *(deps)* Bump ruff from 0.15.8 to 0.15.9 
- *(deps)* Bump mypy from 1.19.1 to 1.20.0 
- Add automatic GitHub Release creation on tag push (#30) 

### Other

- Bump version to 0.5.0 

### Refactor

- Rename metadata attr to _azure_functions_metadata (#67) 

### Documentation

- Add missing exception field to README JSON example (#25) 
- Update README with Azure Functions Python DX Toolkit branding 

### Features

- Add with_context decorator to reduce inject_context() boilerplate (#27) 

### Miscellaneous Tasks

- Release v0.4.1 
- *(deps)* Bump anchore/sbom-action from 0.23.1 to 0.24.0 
- *(deps)* Bump codecov/codecov-action from 5.5.3 to 6.0.0 
- *(deps)* Bump github/codeql-action from 4.33.0 to 4.35.1 
- *(deps)* Bump ruff from 0.15.6 to 0.15.8 
- Use standard pypi environment name for Trusted Publisher 
- Rename publish environment from production to release 
- Unify CI/CD workflow configurations 

### Testing

- Add runtime contract tests for observable behavior (#28) 

### Bug Fixes

- Recursively redact nested dict/list log extras (#7) 
- Treat arbitrary logger kwargs as structured extra fields (#6) 
- Add --resource-group to app insights query and pass E2E_RESOURCE_GROUP env var 
- Add --no-cov and pytest-html artifact to e2e workflow 

### Documentation

- Add before/after terminal screenshots to README 
- Add real Azure e2e test section to testing.md and CHANGELOG 
- Add with_scaffold example showing scaffold integration 

### Features

- Add real Azure e2e tests and CI workflow 

### Miscellaneous Tasks

- Release v0.4.0 
- Remove nonexistent docs/agent-playbook.md ref from AGENTS.md, standardize .gitignore (#9) 
- Add pre-commit config, SBOM/CodeQL workflows, codecov config, adjust coverage threshold (#8) 
- *(deps)* Bump ruff from 0.15.5 to 0.15.6 
- *(deps)* Update mkdocstrings[python] requirement from <1.0 to <2.0 
- *(deps)* Bump anchore/sbom-action from 0.23.0 to 0.23.1 
- Trigger e2e only on release tag push (v*) 
- Upgrade GitHub Actions to Node.js 24 compatible versions 
- Enforce coverage fail_under = 95 
- Add .editorconfig and mypy exclude for examples/ 
- Add keywords to pyproject.toml 
- Add AGENTS.md, Typing classifier, test_public_api, Dev Status 4-Beta, .venv-review in .gitignore 

### Bug Fixes

- Use setattr/getattr in tests to avoid unused type: ignore on Python 3.12+ 

### Documentation

- Reposition README as Azure Functions Python observability helper 

### Features

- P0/P1/P2 improvements — NDJSON fix, host.json None level, context leak reset, ColorFormatter include_extra, functions_formatter param, SamplingFilter, RedactionFilter (v0.3.0) 

### Miscellaneous Tasks

- Add dependabot.yml with pip and github-actions ecosystems 
- Add production environment to release.yml for trusted publishing 

### Testing

- Cover host_config None level, malformed JSON, and unrecognized level paths 

### Documentation

- Overhaul documentation to production quality 
- Sync translated READMEs (ko, ja, zh-CN) with English 
- Unify README — Title Case H1, add Ecosystem, fold Development into Installation; add pyproject.toml classifiers and project URLs 
- Add example-first design section to PRD 
- Fix inaccuracies across 7 doc files against actual source code 
- Expand all documentation pages to production quality 
- Add MkDocs infrastructure with full documentation site 
- Add badges and translated READMEs (ko, ja, zh-CN) 

### Features

- Add 5 runnable example scripts with smoke tests 

### Other

- Bump version to 0.2.2 

### Styling

- Unify tooling — remove black, standardize pre-commit and Makefile 

### Bug Fixes

- Add py.typed marker for PEP 561 compliance (v0.2.1) 

### Bug Fixes

- Resolve ruff I001 import ordering in test files 

### Documentation

- Update PRD with research findings and v0.1.0 scope 
- Add DESIGN.md and AGENT.md for project architecture 
- *(readme)* Rewrite README to match ecosystem structure 
- *(readme)* Add Microsoft trademark disclaimer 
- Add initial PRD 

### Features

- Add JsonFormatter and host.json level conflict warning (v0.2.0) 
- Implement setup_logging with environment-aware configuration 
- Implement ColorFormatter and FunctionLogger wrapper 
- Implement context injection with contextvars and filter 

### Miscellaneous Tasks

- Add project infrastructure to match ecosystem standards 
- Add initial project scaffold 
<!-- generated by git-cliff -->
