# Security Policy

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability, please report it
responsibly and avoid public disclosure until a fix is available.

### Preferred: GitHub Security Advisory

1. Go to the [Security Advisories page](https://github.com/yeongseon/azure-functions-logging-python/security/advisories/new)
2. Click "Report a vulnerability"
3. Submit the details in the private advisory

### Alternative: Email

If you prefer email, contact: yeongseon.choe@gmail.com

### What to Include

* A clear description of the issue
* Steps to reproduce
* Impact assessment
* Suggested mitigation or fix, if available

### Response Timeline

* Initial response: within 48 hours
* Status update: within 7 days

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest release | :white_check_mark: |
| Older releases | :x: |

## Automated controls and permissions

| Control | Runs where | Enforcement |
| --- | --- | --- |
| Bandit 1.9.4 | PR, main, weekly, dispatch (`security.yml`) | Blocking scan; every severity reviewed |
| SHA-pinned Semgrep `p/python` | Same workflow | Existing blocking action; execution evidence added |
| CodeQL `security-extended` | PR, main, weekly | Existing analysis/code-scanning control, unchanged |
| Runtime pip-audit 2.10.1 | Exact candidate wheel, Python 3.11–3.14, base and `otel` closures | Blocking dependency of `publish` |
| Runtime/OTel/development audit | Weekly/dispatch (`dependency-audit.yml`) | Reporting-only, shared classifier |
| SBOM | Weekly/dispatch | Existing installed-wheel inventory, unchanged |

Branch-protection requirements are repository settings, not established by these
workflow files. Existing merge checks, runtime/host smoke and real-Azure certification
remain intact. This change adds no write permission: security workflows and the new
release audit job use only `contents: read`. CodeQL retains `contents: read` and
`security-events: write`; Azure certification retains `contents: read` and
`id-token: write`; PyPI publishing retains `id-token: write` and its trusted-publisher
exception. Publishing still uploads the exact `build` artifact, without rebuilding.

## Static scope and reviewed suppressions

`make security` (also `make security-inventory` / `make security-bandit`) scans every Python file under
`src/`, `examples/` (including `e2e_app` and `otel_app`), `scripts/`, `tools/`, and
`benchmarks/`. Benchmarks are included even when not executed by a particular CI
lane. There are no per-file exclusions within these surfaces. Tests/fixtures are
excluded from this product/tool scan. Bytecode and non-Python artifacts are not
Bandit inputs. Saved host logs and deployment configuration require separate review;
this scan does not claim to analyze Bicep, workflows, or arbitrary log contents.
Inventory must equal the on-disk Python inventory, contain at least 38 files and
have positive LOC. Missing surfaces, errors and unlisted suppressions cannot pass.

Bandit uses `--ignore-nosec`, so existing markers cannot hide findings. The separate
`inline_suppressions` allow-list in `security/bandit-policy.json` requires exact
ID/file/line equality with all markers, including markers that Bandit does not
currently flag. The baseline has 26 markers across seven source files:

| Source module | Count | Rules |
| --- | ---: | --- |
| `_context.py` | 10 | B110 |
| `_filters.py` | 7 | B110 |
| `_host_config.py` | 2 | B110 |
| `_otel.py` | 4 | B110 |
| `_host_instance.py` | 1 | B110 |
| `_redaction.py` | 1 | B112 |
| `_decorator.py` | 1 | B307 |

These are existing best-effort/never-raise contracts and handler-owned annotation
evaluation, not new runtime changes. Retaining a masking-resilience exception is
not proof that runtime failures redact safely; runtime hardening is separate.
The evidence reports marker counts and retains all unsuppressed findings. Other
baseline reviews cover synthetic fixtures, type-narrowing assertions, shell-free
tool invocations, a fixed-host documentation URL checker, and a status-enum false
positive. No global rule exclusions replace review. Local full validation and CI
use the same expanded inventory. Security tools receive
a separate strict mypy invocation (`make security-typecheck`), additive to the
existing project typecheck rather than changing its scope.

## Dependency and exception policy

Every known advisory in the resolved candidate runtime closure blocks release,
regardless of severity. Missing severity is `UNKNOWN`, never assumed low. This is
stricter than a high/critical-only gate and avoids missing-CVSS false greens.
The base closure contains the wheel and required dependencies; a separate matrix
leg audits the wheel's `otel` extra. That extra declares `opentelemetry-api`, not the
example application's separately installed Azure Monitor exporter. Development,
docs and example-only dependencies are not part of the release base/OTel closure.
Each supported interpreter is audited because environment markers affect resolution.
Candidate environments use `venv --without-pip`; audit tools run outside them.
`make security-runtime AUDIT_ARGS="--site-packages <purelib> --candidate-wheel <wheel>"`
verifies wheel METADATA name/version against the installed distribution before
excluding only that first-party candidate. Every installed third-party distribution
is frozen as `name==version` and audited with `--requirement`, `--no-deps`, and
`--disable-pip`; returned inventory must match the full installed closure.
This applies independently to base and `otel` environments. Missing/mismatched
candidate identity, skipped third parties or omitted dependencies block release.
No audit-tool dependencies contaminate the candidate installation.
Scheduled reporting uses `make security-runtime-report` with the same arguments
and preserves non-PASS evidence in reporting-only workflow steps.

Both policy files require maintainer review, exact identifiers, `reason`, `owner`,
`added` and `expires` (ISO dates), and a positive lifetime at most 90 days. Static
exceptions require `reviewed-static` with exact file/line. Dependency exceptions
require exact package/advisory and `not-affected` (independently verified evidence)
or `fix-not-available` (only while no fixed version is listed). Package separators
are normalized; advisory aliases are not silently ignored. Expired entries block
even when unused; stale entries are counted for removal. The dependency policy
starts empty. Do not add blanket skips or new inline markers instead of review.
When runtime changes move existing lines, re-review the exact allow-list rather
than broadening it; automation and runtime branches must reconcile that inventory.

## Failure semantics and recovery

Helpers exit PASS=0, FAIL=1 (unexcepted findings/expired exceptions), TOOL_ERROR=2
(crash, timeout, missing/invalid JSON, invalid policy, zero audited packages or
tool/database failure), INCOMPLETE=3 (empty static scan, missing coverage, skipped
packages, unlisted inline suppressions or absent execution evidence). Every non-PASS
blocks release. Scheduled reporting preserves the same status but does not gate a
release. `make security-semgrep SCAN_OUTCOME=success` records INCOMPLETE with
"action outcome only", not PASS, because no structured results or analysed
inventory are available. The target tolerates exactly evidence exit 3 while the
SHA-pinned Semgrep action remains the gate. Failure is conservatively
TOOL_ERROR with unknown findings count, skipped/cancelled INCOMPLETE. Its original
failing step remains blocking; an action failure alone is not called a vulnerability.
`make security-host` is the opt-in local host test; it requires the e2e host prerequisites.

Advisory database outages can delay publication: this is an intentional availability
tradeoff for fail-closed verification. Bounded timeouts limit hangs. Never bypass
the gate. Retry the same unchanged tagged candidate with
`gh workflow run publish-pypi.yml --ref vX.Y.Z`. Dispatch takes no inputs; use the
existing tag as its ref, not main. Corrections to code/workflows must fix forward
to a new release candidate; never move/reuse the old tag.

## Evidence and production boundaries

Helpers emit schema-version-1 `security-results/**/summary.json` containing scope,
check/status, tool exit status, counts, tool versions, suppression counts, applied
exception identifiers and allow-listed finding IDs, relative paths/lines, severities,
confidence and package identifiers. Human-readable status/counts go to Job Summary.
Uploads run `if: always()` with unique artifact names and fail if evidence is absent.
Installation/setup failures can prevent report creation; missing artifacts remain
an explicit failure, never PASS. Generated local evidence is gitignored.

Security evidence must never contain credentials, connection strings, authorization
headers or original user payloads. Helpers do not retain raw scanner stdout/stderr,
source snippets, advisory descriptions or policy reasons; malformed diagnostics
produce fixed messages. Deterministic canary tests guard JSON and Markdown output.
This guarantee covers these evidence helpers, not all pre-existing host/exporter logs.
A finding is a **code/config review finding until runtime impact is independently
demonstrated**; a clean scan does not prove the absence of vulnerabilities.

Examples are local-only synthetic demonstrations except `e2e_app`, which is also
ephemeral public Azure certification infrastructure. Anonymous routes and disabled
sampling are test conveniences, not production defaults. Query parameters such as
`correlation_id` and `order_id` reach logs: use synthetic identifiers only, never
real payloads, credentials, headers or PII. The OTel masking example uses a dummy
value; do not rely on it as a complete privacy profile. For secure logging
configuration, see the redaction documentation. This branch adds no runtime API.

Production deployments need explicit authentication/authorization, restricted
ingress, HTTPS/minimum TLS, private blobs, managed identities and storage RBAC,
restricted telemetry access/retention, and appropriate sampling. Review of examples
found no request-body/header dump or printed connection string/instrumentation key;
user-controlled identifiers still require care. `infra/main.bicep` enforces HTTPS,
storage TLS 1.2 and private blobs, but retains shared-key storage connection strings,
public network reachability, no declared managed identity, and an Application
Insights connection-string deployment output. The Azure workflow emits deployment
outputs, so that output is a telemetry-configuration disclosure risk; do not treat
deployment logs as sanitized security evidence. Removing outputs, moving storage to
identity/RBAC, private endpoints, explicit app/SCM TLS and authenticated certification
routes require real-Azure validation. They are follow-ups, not changes in this port.
Host diagnostics/saved logs also need an independently verified allow-list and
retention review before accepting real user data. Use synthetic data only in CI.
