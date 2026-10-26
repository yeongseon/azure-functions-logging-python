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

## Automated security controls

| Control | Where it runs | When | Effect |
| ------- | ------------- | ---- | ------ |
| Bandit over `src examples scripts tools benchmarks`; an empty, missing or unparsable scope fails (`make security`) | `security.yml` job `bandit` | pull requests, pushes to `main`, weekly | required check; sanitized JSON and job summary |
| Pinned Semgrep action plus pinned CLI scope/evidence scan (`p/python`, `make security-semgrep`); CodeQL (`security-extended`) | `security.yml` job `semgrep`; `codeql.yml` job `Analyze` | same | required checks; sanitized Semgrep JSON and job summary; CodeQL code-scanning results |
| `pip-audit` of runtime and development dependencies | `dependency-audit.yml` | weekly and on demand | reporting only (`continue-on-error`); never blocks |
| `pip-audit` of the candidate wheel's runtime dependencies | `publish-pypi.yml` job `runtime-dependency-audit` | `v*` tags and manual dispatch on a tag; **not** pull requests | blocks `publish` |

### Release gate: known advisories in the runtime dependencies

`runtime-dependency-audit` installs the downloaded candidate wheel (the exact artifact `publish` uploads) into a clean virtual environment, with and without `[otel]`, on Python 3.11 and 3.14. These bracket the supported Python range and can resolve different compatible dependency versions; no untested SDK major is implicitly certified. Each cell runs `pip freeze --exclude azure-functions-logging`, `test -s` and `pip-audit==2.10.1 --no-deps --disable-pip --strict`, and fails on any known advisory, an empty dependency list or a package `pip-audit` cannot audit. `pip-audit` reports no severity, so every advisory blocks (a conservative policy stronger than a severity threshold). The audit queries PyPI: if it is unreachable the release stays blocked until a retry passes (`gh workflow run publish-pypi.yml --ref vX.Y.Z`). Each cell uploads its JSON report (`runtime-audit-*`, 30 days).

An advisory that cannot be fixed yet may be waived for at most 90 days in `security/runtime-advisory-exceptions.txt`, one line each:

```text
ADVISORY-ID owner added expires reason...
```

`added` and `expires` are ISO dates. A waiver that is expired, not yet added, malformed or longer than 90 days fails the gate (`tools/runtime_audit_args.py`). The gate reads the file from the tagged commit, so a waiver must be on `main` before the Release PR is merged; after a failed tag, fix forward with the next release. Pull-request CI does not run the gate, so check an edit with `python tools/runtime_audit_args.py security/runtime-advisory-exceptions.txt`.

### Scanner scope and disclosure-safe evidence

The explicit Python inventory includes the installed library, executable examples,
scripts, CI helper tools and benchmarks. Unit-test fixtures, documentation prose,
virtual environments and distribution copies are not production Python scan
targets. CodeQL retains its repository Python analysis and security-extended
queries. Bicep and workflow permissions require configuration review, not a claim
that a Python scanner certified IaC.

`tools/security_reports.py` compares each scanner's reported paths to every Python
file under the declared scopes. Missing directories, missing files, zero files,
parse/engine errors, malformed reports and unexpected exit status fail closed.
Semgrep's evidence scan disables inline `nosemgrep` suppressions. Bandit retains
existing reviewed inline `nosec` annotations and reports their count; code review
must justify changes to them. Source snippets, diagnostic text, finding messages,
absolute paths and payloads are never copied into published scanner artifacts:
the allowlist contains scanner name, outcome, exit status and numeric counts only.
Raw scanner output is temporary and deleted after summary generation. Findings
and tool errors remain distinct; both block. Failed jobs still upload the safe
summary. Rerun locally to investigate findings rather than publishing raw source
or secret-bearing diagnostic text. Scanner installation failure blocks the job
and cannot produce a clean evidence record.

Dependency audit reports describe public package versions and advisory IDs, not
application payloads. Runtime advisories gate publishing; development advisories
remain visible reports. No scanner replaces Bandit, Semgrep, CodeQL, SBOM, wheel
reuse, SHA pins, OIDC publishing or Azure release certification.

### Production versus demonstration boundaries

Production redaction is opt-in: configure exporters and logging first, then call
`configure_secure_redaction()`. It applies bounded fail-closed key/pattern masking
to current handlers; protect late handlers explicitly. Ordinary `setup_logging()`
does not disable it. The eight-keyword setup ceiling is unchanged. See
[secure configuration](docs/configuration.md#secure-production-configuration) for
ordering, exception behavior, Unicode and arbitrary-secret limitations. Synthetic
tests exercise console/custom formatters, JSON and OTel sinks, nested/flattened
fields, cyclic/opaque values and concurrency without asserting cloud ingestion.

`infra/main.bicep`, the anonymous HTTP examples and development storage connection
settings are temporary/local test infrastructure, not hardened production
templates. The template enables HTTPS-only access, storage TLS 1.2 and disables
public blob access, but uses storage keys and public HTTP endpoints rather than
managed identity and application authentication. Production deployments must
choose authentication/authorization, identity, network restrictions and telemetry
retention for their own trust boundary. Do not expose example routes to user data
or reuse development credentials. The deployment workflow suppresses secret-bearing
deployment output; live Azure log proof remains separately tracked in #625 and
has not been established by static checks or local host tests.
