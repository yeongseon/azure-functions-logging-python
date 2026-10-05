# Changelog

All notable changes to this project will be documented in this file.
## [0.13.4](https://github.com/yeongseon/azure-functions-logging-python/compare/v0.13.3...v0.13.4) (2026-10-05)


### Bug Fixes

* **decorator:** keep concrete Context annotations for None-defaulted parameters ([#531](https://github.com/yeongseon/azure-functions-logging-python/issues/531)) ([c890c6b](https://github.com/yeongseon/azure-functions-logging-python/commit/c890c6b38679218fd4fafe552ebc17d04b6aebc8))
* **deps:** align azure-functions floor at 1.21.0 ([#528](https://github.com/yeongseon/azure-functions-logging-python/issues/528)) ([2133818](https://github.com/yeongseon/azure-functions-logging-python/commit/213381803f5f8dce62724afa3a2a41649562f084))

## [0.13.3](https://github.com/yeongseon/azure-functions-logging-python/compare/v0.13.2...v0.13.3) (2026-10-04)


### Bug Fixes

* **decorator:** resolve postponed annotations against the handler module ([#521](https://github.com/yeongseon/azure-functions-logging-python/issues/521)) ([535a377](https://github.com/yeongseon/azure-functions-logging-python/commit/535a3771ad8161bd7a621d4a0db0c04f1a580024))

## [0.13.2](https://github.com/yeongseon/azure-functions-logging-python/compare/v0.13.1...v0.13.2) (2026-10-03)


### Bug Fixes

* **context:** avoid KeyError when extra keys collide with context vars ([#517](https://github.com/yeongseon/azure-functions-logging-python/issues/517)) ([12ba17e](https://github.com/yeongseon/azure-functions-logging-python/commit/12ba17e72a48d3352d2050470a2471695ae136c0))
* **decorator:** restore context safely when a generator closes in another task ([#518](https://github.com/yeongseon/azure-functions-logging-python/issues/518)) ([346cf44](https://github.com/yeongseon/azure-functions-logging-python/commit/346cf44d096f7d1e0f5f578938d4ceea6ea34505))
* **logger:** accept level, msg and args as extra keys ([#516](https://github.com/yeongseon/azure-functions-logging-python/issues/516)) ([47deb60](https://github.com/yeongseon/azure-functions-logging-python/commit/47deb60c3d9a6509d926a696bab8ad859f100651))
* **redaction:** cover camelCase secret keys, APIM keys and exception text ([#513](https://github.com/yeongseon/azure-functions-logging-python/issues/513)) ([b19c284](https://github.com/yeongseon/azure-functions-logging-python/commit/b19c284613fb2a26f9681cc6000bd47c42ced87e))
* **setup:** leave OpenTelemetry handlers unformatted ([#515](https://github.com/yeongseon/azure-functions-logging-python/issues/515)) ([25a70d5](https://github.com/yeongseon/azure-functions-logging-python/commit/25a70d5dcd295962f666a15b08b5d4ba6ead326e))

## [0.13.1](https://github.com/yeongseon/azure-functions-logging-python/compare/v0.13.0...v0.13.1) (2026-10-02)


### Bug Fixes

* **context:** preserve context during generator iteration ([#500](https://github.com/yeongseon/azure-functions-logging-python/issues/500)) ([c26afe5](https://github.com/yeongseon/azure-functions-logging-python/commit/c26afe56d30cf1d56c869bb6bc9e8bc85f1525e4))
* **json:** include stack_info in JsonFormatter output ([#504](https://github.com/yeongseon/azure-functions-logging-python/issues/504)) ([428f842](https://github.com/yeongseon/azure-functions-logging-python/commit/428f84258c4d63e08012e1c91ea99fedac3b0b28))
* **json:** serialize non-finite floats as strings ([#501](https://github.com/yeongseon/azure-functions-logging-python/issues/501)) ([200afce](https://github.com/yeongseon/azure-functions-logging-python/commit/200afce9482912d2081e5fe9397175752b280f96))

## [0.13.0](https://github.com/yeongseon/azure-functions-logging-python/compare/v0.12.1...v0.13.0) (2026-10-01)


### Bug Fixes

* **compat:** deprecate Python 3.10 ahead of its removal ([#488](https://github.com/yeongseon/azure-functions-logging-python/issues/488)) ([137e05f](https://github.com/yeongseon/azure-functions-logging-python/commit/137e05f570fc074122c5882b06b9d8fd24452a12))
* **context:** leave caller-owned executors running on exit ([#490](https://github.com/yeongseon/azure-functions-logging-python/issues/490)) ([da4280d](https://github.com/yeongseon/azure-functions-logging-python/commit/da4280d77ee3bbe3c0e922f7bc73282d14bdf52c))
* **decorator:** reject kwargs-only handlers in strict context mode ([#491](https://github.com/yeongseon/azure-functions-logging-python/issues/491)) ([4abdf0c](https://github.com/yeongseon/azure-functions-logging-python/commit/4abdf0c00be342143a2f5273c1271fcf9b53b2c2))
* **redaction:** mask cookie and API-key headers by default ([#489](https://github.com/yeongseon/azure-functions-logging-python/issues/489)) ([92ae5aa](https://github.com/yeongseon/azure-functions-logging-python/commit/92ae5aa5548a3578da36af83a230ce1aeab6858f))


### Miscellaneous Tasks

* release 0.13.0 ([83df5e8](https://github.com/yeongseon/azure-functions-logging-python/commit/83df5e84a1b72e4f90439a9da81488170d98d9af))

## [0.12.1](https://github.com/yeongseon/azure-functions-logging-python/compare/v0.12.0...v0.12.1) (2026-09-29)


### Bug Fixes

* **ci:** unbreak the OTel canary, correct SECURITY URL, release wording and stale inputs ([#466](https://github.com/yeongseon/azure-functions-logging-python/issues/466)) ([3e53755](https://github.com/yeongseon/azure-functions-logging-python/commit/3e53755864be93c741d3c1e927e758feb8c84a24))


### Documentation

* align the contributor contract with the actual configuration ([#464](https://github.com/yeongseon/azure-functions-logging-python/issues/464)) ([9343ea0](https://github.com/yeongseon/azure-functions-logging-python/commit/9343ea043cfcad1515951e6c0200095173bf778f))


### Testing

* **redaction:** add free-text masking false-positive corpus + benchmark ([#446](https://github.com/yeongseon/azure-functions-logging-python/issues/446)) ([47477b9](https://github.com/yeongseon/azure-functions-logging-python/commit/47477b90c371ec4d5e23d6781a9349dd68e230e9)), closes [#445](https://github.com/yeongseon/azure-functions-logging-python/issues/445)


### Miscellaneous Tasks

* adopt release-please and gate PyPI on in-chain Azure e2e ([#474](https://github.com/yeongseon/azure-functions-logging-python/issues/474)) ([7604ca0](https://github.com/yeongseon/azure-functions-logging-python/commit/7604ca0fe85211e3175ed1d7404106ab22f95759))
* allow build/ branch prefix in branch-naming validation ([#449](https://github.com/yeongseon/azure-functions-logging-python/issues/449)) ([7a636b3](https://github.com/yeongseon/azure-functions-logging-python/commit/7a636b3d880b7faa9e8974dff138ce08fd8b2340))
* **deps:** bump ruff in the python-dependencies group ([#450](https://github.com/yeongseon/azure-functions-logging-python/issues/450)) ([0c0a5f6](https://github.com/yeongseon/azure-functions-logging-python/commit/0c0a5f65a89569b18729a64bc348d6a2fef73dd9))
* **deps:** bump the github-actions group with 2 updates ([#451](https://github.com/yeongseon/azure-functions-logging-python/issues/451)) ([8fd80fd](https://github.com/yeongseon/azure-functions-logging-python/commit/8fd80fd801bdaf82e79c045e3508aaa01dede27a))
* **deps:** bump the github-actions group with 3 updates ([#460](https://github.com/yeongseon/azure-functions-logging-python/issues/460)) ([3639504](https://github.com/yeongseon/azure-functions-logging-python/commit/36395047c2c9de95c71ac77ee9642e7331b29667))
* gate unformatted changed Python files in the quality job ([#462](https://github.com/yeongseon/azure-functions-logging-python/issues/462)) ([16a6521](https://github.com/yeongseon/azure-functions-logging-python/commit/16a652124e7d75726898f199764006f1c2d3b772))
* ignore Playwright MCP session artifacts ([376fc8f](https://github.com/yeongseon/azure-functions-logging-python/commit/376fc8f1ea43aebd4090534a393a064562b49459))
* ignore uv.lock ([#470](https://github.com/yeongseon/azure-functions-logging-python/issues/470)) ([7720875](https://github.com/yeongseon/azure-functions-logging-python/commit/7720875e9b591827d922b89267373bec5828dc23)), closes [#469](https://github.com/yeongseon/azure-functions-logging-python/issues/469)
* modernize typing and pin ruff, complete AGENTS.md, unify Azure e2e auth ([#472](https://github.com/yeongseon/azure-functions-logging-python/issues/472)) ([61d35cf](https://github.com/yeongseon/azure-functions-logging-python/commit/61d35cf929bb0bf6c3658036849465acbf7e1054))
* run OTel nightly on the upgraded deps, not the pinned hatch env ([#448](https://github.com/yeongseon/azure-functions-logging-python/issues/448)) ([84ba996](https://github.com/yeongseon/azure-functions-logging-python/commit/84ba996d0d60683b2a0215d70fc61b694242ae0c))
* wire and harden the hatch default-env-pin lint ([#447](https://github.com/yeongseon/azure-functions-logging-python/issues/447)) ([ec7a1ac](https://github.com/yeongseon/azure-functions-logging-python/commit/ec7a1ac241baeb143ffe671bfed96feb40a58618))

## [0.12.0] - 2026-09-09

### Features

- *(context)* Add propagating_executor for auto worker-thread context propagation (#444) 
- *(redaction)* Mask secrets embedded in free-text log messages (#441) 

### Miscellaneous Tasks

- *(deps)* Bump ruff in the python-dependencies group (#442) 
- *(ci)* Group dependabot updates + auto-merge patch/minor (#392) 
- Allow test/ and refactor/ branch prefixes to match commit types (#440) 
- *(deps)* Bump github/codeql-action init+analyze to v4.37.9 (#439) 
- *(deps)* Bump anchore/sbom-action from 0.24.0 to 0.24.2 (#420) 
- *(deps)* Bump softprops/action-gh-release from 3.0.2 to 3.0.3 (#419) 
- *(deps)* Bump ruff from 0.16.3 to 0.16.5 (#418) 

### Other

- Bump version to 0.12.0 

### Testing

- *(otel)* Promote OTel spike suite to formal contract tests (#438) 
## [0.11.0] - 2026-09-08

### Bug Fixes

- *(ci)* Test matrix silently runs Python 3.10 due to hatch default-env pin (#423) 
- *(ci)* Reset artifact action pins to canonical v4 + Dependabot ignore (#399) 
- *(setup)* Warn when extra_context_vars is ignored under use_record_factory (#369) 
- *(setup)* Stop double-logging on standalone named loggers (#362) 
- *(otel)* Don't overwrite an active local span in activated_trace_context (#361) 
- *(formatter)* Suppress color outside TTY and honor NO_COLOR (#352) 
- *(logger)* Report user call sites from FunctionLogger (#350) 

### Documentation

- Update changelog 
- 0.11.0 follow-ups (#425, #426, #427) (#430) 
- Add "How correlation works" mechanism page and cross-links (#409) 
- *(logging)* Codify setup_logging complexity ceiling (no 9th kwarg) (#397) 
- *(logging)* Add explicit maturity/status marker to README (#396) 
- *(setup)* Define and document setup_logging() reconfiguration semantics (#386) 
- Sync symptom-driven examples into translated READMEs (#377) 
- Refine scope docs, add symptom examples & benchmarks (#376) 
- *(context)* Align ContextFilter docstring with the default injection mode (#370) 
- Remove redundant content from README (#357) 
- Recapture local demo screenshots from real terminal output (#356) 
- Refresh App Insights screenshots with real PII-free captures (#355) 
- *(examples)* Show Application Insights query results for each example (#354) 
- Unify basic-usage guides onto one recommended path and fix contradictions (#345) 
- Fix stale repo URLs in module docstrings (#351) 
- *(opentelemetry)* Add verified App Insights query captures (#344) 

### Features

- *(decorator)* Optional invocation lifecycle auto-logging (start/end/duration) (#387) 
- *(context)* Add background-thread invocation context propagation helper (#385) 
- *(context)* Support extra_context_vars in use_record_factory mode (#384) 
- Detect ineffective @with_context at decoration time (#383) 
- *(logger)* Delegate unimplemented stdlib Logger attributes on FunctionLogger (#368) 

### Miscellaneous Tasks

- Guard against hatch default-env pin hiding the CI matrix (#433) (#434) 
- *(release)* Drop GITHUB_TOKEN scopes on notify-cookbook job (#413) (#431) 
- Codify open issue-creation as fleet policy in AGENTS.md (#429) (#432) 
- *(docs)* Add external-link tag-integrity check (#410) 
- Notify cookbook to re-run e2e after PyPI release (#404) 
- *(logging)* Scheduled Core Tools host-boot matrix smoke on e2e app (#398) 
- *(deps)* Bump actions/upload-artifact from 4.6.2 to 7.0.1 (#372) 
- *(deps)* Bump actions/download-artifact from 4.3.0 to 8.0.1 (#371) 
- *(deps)* Bump github/codeql-action/analyze from 4.37.6 to 4.37.7 (#391) 
- *(deps)* Bump github/codeql-action/init from 4.37.6 to 4.37.7 (#390) 
- *(deps)* Bump mypy from 2.3.0 to 2.3.1 (#389) 
- *(deps)* Bump ruff from 0.16.2 to 0.16.3 (#388) 
- *(e2e)* Certify the release candidate wheel, not the PyPI build (#346) 

### Other

- Bump version to 0.11.0 
- *(deps)* Add Dependabot cooldown to age new releases (#422) 

### Refactor

- P3 cleanup — dead code, field-name SSOT, decorator perf (#364) 

### Testing

- *(e2e)* Assert correlation-doc claims in host-boot matrix smoke (#411) 
## [0.10.2] - 2026-08-14

### Documentation

- Update changelog 
- Consolidate official documentation URL onto yeongseon.dev (#339) 
- Sync context-field API in docs (span_id, host_instance_id, setup_logging params) (#331) 
- *(i18n)* Adopt best-effort translation policy with staleness banners (#330) 
- Sync context-field API in docs (span_id, host_instance_id, setup_logging params) (#321) 

### Miscellaneous Tasks

- Stop auto-deploying docs to GitHub Pages (#341) 
- Adopt Renovate for GitHub Actions bumps (#337) 
- *(ci)* Normalize action version-comment labels (#335) 
- Add workflow pin-hygiene lint (#333) 
- Add release-gate workflow drift lint (#328) 
- Normalize release-gate action pins to canonical SHAs (#326) 
- Add tiered pre-publish runtime gate with real-Azure certification (#319) 
- Ignore agent orchestration state (.sisyphus/, .omc/) (#324) 
- Bump ruff to 0.16.2 and repair pre-commit hooks (#318) 
- Drop stale noqa on opentelemetry.context import (#317) 

### Other

- Bump version to 0.10.2 
## [0.10.1] - 2026-08-12

### Bug Fixes

- *(otel)* Skip attaching invalid extracted span context (#316) 

### Documentation

- Update changelog 
- Add Branch Hygiene section to AGENTS.md 

### Other

- Bump version to 0.10.1 
## [0.10.0] - 2026-08-11

### Documentation

- Update changelog 
- *(release)* Require cookbook dogfood verification after publish 

### Features

- Add host_instance_id field for scaled-out worker attribution (#309) 

### Miscellaneous Tasks

- *(deps)* Bump ruff from 0.16.0 to 0.16.1 (#312) 
- *(deps)* Bump azure/login from 3.0.0 to 3.0.1 (#314) 
- *(codeql)* Bump codeql-action init+analyze to v4.37.6 together 

### Other

- Bump version to 0.10.0 
## [0.9.0] - 2026-08-09

### Bug Fixes

- *(host-config)* Treat Azure Monitor connection string as an OTel export signal (#306) 
- *(redaction)* Mask any sensitive dotted segment to prevent PII leak (#305) 
- *(filters)* Redact flattened dotted keys to prevent PII leak (#294) 

### Documentation

- Update changelog 
- Soften OpenTelemetry trace-correlation gap wording (#307) 
- Emphasize Python-only OpenTelemetry invocation-middleware gap in READMEs (#301) 
- *(otel)* Reframe distributed-tracing non-goal as "binds host trace context, does not trace" (#297) 
- *(otel)* Clarify record mutation, late-handler filters, and root-logger wording (#296) 
- *(agents)* Consolidate AGENT.md into AGENTS.md 

### Features

- *(metadata)* Document logging namespace key as cross-repo ordering contract (#310) (#311) 
- Make trace-context activation strictly opt-in and remove factory shims (#295) 

### Miscellaneous Tasks

- Track issue priority via priority:* labels instead of body line 

### Other

- Bump version to 0.9.0 

### Testing

- *(otel)* Cover public-API trace correlation + redaction end-to-end (#300) 
## [0.8.1] - 2026-08-04

### Bug Fixes

- *(filters)* Harden dict flattening; add OTel correlation test and docs 
- *(otel)* Normalize traceparent hex to lowercase and cache is_available 

### Documentation

- Update changelog 
- *(otel)* Document that in-handler spans become children of the host span 

### Miscellaneous Tasks

- *(deps)* Bump actions/setup-python from 6.3.0 to 7.0.0 
- *(deps)* Bump actions/setup-node from 6.4.0 to 7.0.0 
- *(deps)* Bump actions/stale from 10.4.0 to 11.0.0 
- *(deps)* Bump actions/checkout from 7.0.0 to 7.0.1 

### Other

- Bump version to 0.8.1 
## [0.8.0] - 2026-08-04

### Bug Fixes

- *(ci)* Replace fragile Core Tools apt install with pinned npm (#220) 

### Documentation

- Update changelog 
- *(otel)* Add opentelemetry guide and examples/otel_app (#258) 
- Require translation sync in the same PR as English changes (Closes #238) (#239) 
- Correct azure-functions-db description in ecosystem table (#237) 
- Add ## Disclaimer heading (#234) (#235) 
- De-duplicate README against docs/ and sync i18n variants (#227) 

### Features

- *(diagnostics)* Warn on OpenTelemetry logging misconfiguration (#256) 
- *(otel)* Activate host W3C trace context for OTel log correlation (#255) 
- *(otel)* Add AttributeFlattenFilter to prevent nested-dict attribute drop (#260) 
- *(json)* Emit span_id in JsonFormatter output (#257) 
- *(context)* Expand _extract_trace_id into _extract_trace_context (#254) 
- *(context)* Add extra_context_vars extension point (#229) 
- *(context)* Add uninstall_context_factory restore API (#221) 

### Miscellaneous Tasks

- *(lint)* Gate ruff format --check in style script 
- *(deps)* Bump github/codeql-action/init from 4.37.1 to 4.37.3 (#246) 
- *(deps)* Bump actions/setup-node from 6.4.0 to 7.0.0 (#245) 
- *(deps)* Bump actions/setup-python from 6.3.0 to 7.0.0 (#244) 
- *(deps)* Bump actions/checkout from 7.0.0 to 7.0.1 (#243) 
- *(deps)* Bump ruff from 0.15.22 to 0.16.0 (#242) 
- *(docs)* Add mermaid render lint to catch diagram syntax regressions (#233) 
- *(deps)* Bump github/codeql-action/analyze from 4.37.0 to 4.37.1 (#224) 
- *(deps)* Bump github/codeql-action/init from 4.37.0 to 4.37.1 (#226) 
- *(deps)* Bump softprops/action-gh-release from 3.0.1 to 3.0.2 (#222) 
- *(deps)* Bump mypy from 2.2.0 to 2.3.0 (#223) 
- *(deps)* Bump ruff from 0.15.21 to 0.15.22 (#225) 

### Other

- Bump version to 0.8.0 

### Refactor

- *(context)* Extract shared worker-compat metadata helper (#232) 
- Deprecate install_context_factory() in favor of setup_logging(use_record_factory=True) (#230) 
- *(metadata)* Type the logging cross-package metadata contract (#228) 

### Testing

- *(otel)* Verify Redaction/Sampling/Flatten compose through OTel handler (#259) 
## [0.7.7] - 2026-07-18

### Bug Fixes

- *(filters)* Normalize hyphenated keys in RedactionFilter and expand default set (#178) 
- *(host_config)* Merge host.json and app setting levels to eliminate false positive warnings (#177) 
- *(filters)* Expand RedactionFilter default sensitive key set (#170) 
- *(filters)* Expand default sensitive key set (#162) 
- *(setup)* Remove ContextFilter when enabling record factory (#160) 

### Documentation

- Update changelog 
- Document context helpers and add api-coverage guard (#212) 
- Add pipeline diagram to READMEs and clarify injection modes (#213) 
- Add discoverability metadata (pepy badge + llms.txt) (#219) 
- Align AGENT.md lint/merge-gate commands with Makefile (#206) 
- *(setup)* Clarify root logger interaction contract (#187) 
- Sync README and llms.txt with v0.7.x operational behavior (#168) 
- *(assets)* Add Application Insights portal screenshots for before/after comparison (#158) 

### Features

- *(filters)* Add stale bucket eviction for SamplingFilter per_logger mode (#179) 
- Implement host override detection and per-logger sampling (#173) 
- *(json)* Add optional native string truncation to JsonFormatter (#166) 
- *(host_config)* Discover host.json from AzureWebJobsScriptRoot env var (#164) 

### Miscellaneous Tasks

- *(deps)* Bump github/codeql-action/analyze from 4.36.2 to 4.37.0 (#203) 
- *(deps)* Bump github/codeql-action/init from 4.36.2 to 4.37.0 (#202) 
- *(deps)* Bump actions/setup-python from 6.2.0 to 6.3.0 (#197) 
- *(deps)* Bump actions/stale from 10.3.0 to 10.4.0 (#200) 
- *(deps)* Bump mypy from 2.1.0 to 2.2.0 (#201) 
- *(deps)* Bump ruff from 0.15.20 to 0.15.21 (#204) 
- *(ci)* Pin external actions to commit SHAs and document policy (#196) 
- *(deps)* Bump actions/checkout from 6 to 7 (#191) 
- *(deps)* Bump softprops/action-gh-release from 3.0.0 to 3.0.1 (#192) 
- *(deps)* Bump ruff from 0.15.16 to 0.15.20 (#194) 
- *(deps)* Bump codecov/codecov-action from 6.0.1 to 7.0.0 (#189) 

### Other

- Bump version to 0.7.7 

### Refactor

- *(context)* De-duplicate reserved keys and redaction logic (#217) 

### Testing

- Assert ContextFilter and LogRecordFactory enrich records at parity (#215) 
## [0.7.6] - 2026-06-07

### Bug Fixes

- Post-v0.7.5 Oracle review — factory isolation, azure state key, handler WeakSet, redaction fail-closed (#156) 

### Documentation

- Update changelog 

### Miscellaneous Tasks

- *(deps)* Bump ruff from 0.15.12 to 0.15.16 (#149) 
- *(deps)* Bump github/codeql-action from 4.35.4 to 4.36.2 (#148) 
- *(deps)* Bump codecov/codecov-action from 6.0.0 to 6.0.1 (#145) 
- *(deps)* Bump actions/stale from 10.2.0 to 10.3.0 (#143) 
- *(deps)* Bump mypy from 2.0.0 to 2.1.0 (#141) 

### Other

- Bump version to 0.7.6 
## [0.7.5] - 2026-06-07

### Bug Fixes

- *(setup)* Recover Azure mode when host handlers attach after first call (#154) 
- *(host_config)* Narrow host.json conflict warnings to user-relevant categories (#153) 
- *(filters)* Harden RedactionFilter with cycle guard and depth limit (#152) 
- *(context)* Make cold-start detection thread-safe (#151) 

### Documentation

- Update changelog 

### Other

- Bump version to 0.7.5 

### Refactor

- *(logger)* Centralize standard LogRecord field definitions (#150) 
## [0.7.4] - 2026-05-23

### Bug Fixes

- *(decorator)* Drop functools.wraps to prevent Azure worker following __wrapped__ 

### Documentation

- Update changelog 

### Other

- Bump version to 0.7.4 
## [0.7.3] - 2026-05-14

### Documentation

- Update changelog 

### Other

- Bump version to 0.7.3 

### Testing

- *(public-api)* Derive version assertion from distribution metadata 
## [0.7.2] - 2026-05-12

### Bug Fixes

- *(setup)* Preserve factory-injected context when use_record_factory=True (#132) 
- *(context)* Tighten W3C traceparent validation in _extract_trace_id (#109) 
- *(json)* Make JsonFormatter fully fail-safe in format() (#106) 

### Documentation

- Update changelog 
- Scope output examples to environment and fix SamplingFilter attachment (oracle iter 7) (#127) 
- Clarify functions_formatter scope, fix color-format pattern and stray fence (oracle iter 6) (#126) 
- Align quickstart with NDJSON output, fix host warning text and llms-full imports (oracle iter 5) (#125) 
- Clarify root-logger filter scope and traceparent version semantics (oracle iter 4) (#124) 
- Tighten env detection, trace_id wording, App Insights hedge, llms.txt signature (oracle iter 3) (#123) 
- Precise environment-aware behavior summary (oracle iter 2) (#122) 
- Address oracle iteration 1 findings (root logger contract, redaction, runnable snippets) (#121) 
- P2 polish for type accuracy and feature visibility (#120) 
- Fix broken runnable snippets in llms.txt and llms-full.txt (#119) 
- Correct API documentation in llms.txt and llms-full.txt (#118) 
- *(llms-full)* Replace bare inject_context() with safe context patterns (#117) 
- Clarify Azure Functions JSON output requires functions_formatter (#116) 
- Sync multilingual README, llms.txt, and docs with v0.7.x API (#110) 

### Features

- *(setup)* Add use_record_factory option and JSON-safe extra coercion (#131) 
- *(json)* Truncate oversized fallback values in JsonFormatter (#129) 
- *(logger)* Add FunctionLogger.log() and hasHandlers() for stdlib parity (#108) 
- *(host-config)* Make host.json discovery deterministic and bounded (#107) 

### Miscellaneous Tasks

- *(changelog)* Restore per-version section headers in cliff template 
- *(deps)* Bump mypy from 1.20.2 to 2.0.0 
- *(deps)* Bump github/codeql-action from 4.35.3 to 4.35.4 

### Other

- Bump version to 0.7.2 

### Refactor

- *(logger)* Derive reserved LogRecord keys from logging.makeLogRecord (#83) (#130) 
## [0.7.1] - 2026-05-08

### Bug Fixes

- *(logger)* Correct merge precedence to bind < extra < kwargs 

### Documentation

- Regenerate changelog for v0.7.1 

### Miscellaneous Tasks

- Bump version to 0.7.1 

### Refactor

- *(logger)* Prevent silent overwrite in _sanitize_extra() on rename collision 

### Testing

- *(logger)* Add regression tests for control kwarg leakage and sanitize double-prefix 
## [0.7.0] - 2026-05-08

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
## [0.5.3] - 2026-04-26

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
## [0.5.2] - 2026-04-26

### Bug Fixes

- Release pipeline + correctness hotfixes (#77) (#80) 

### Documentation

- Update changelog 
- Add Request Flow and Runtime Relationship section to architecture 

### Miscellaneous Tasks

- *(deps)* Bump actions/github-script from 8.0.0 to 9.0.0 
- *(deps)* Bump actions/upload-artifact from 7.0.0 to 7.0.1 
## [0.5.0] - 2026-04-10

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
## [0.4.1] - 2026-03-29

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
## [0.4.0] - 2026-03-21

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
## [0.3.0] - 2026-03-15

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
## [0.2.2] - 2026-03-14

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
## [0.2.1] - 2026-03-12

### Bug Fixes

- Add py.typed marker for PEP 561 compliance (v0.2.1) 
## [0.2.0] - 2026-03-12

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
