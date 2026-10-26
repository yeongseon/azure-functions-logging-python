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
| Bandit over `src examples scripts tools benchmarks`; an empty, missing or unparsable scope fails (`make security`) | `security.yml` job `bandit` | pull requests, pushes to `main`, weekly | required check |
| Semgrep (`p/python`); CodeQL (`security-extended`) | `security.yml` job `semgrep`; `codeql.yml` job `Analyze` | same | required checks |
| `pip-audit` of runtime and development dependencies | `dependency-audit.yml` | weekly and on demand | reporting only (`continue-on-error`); never blocks |
| `pip-audit` of the candidate wheel's runtime dependencies | `publish-pypi.yml` job `runtime-dependency-audit` | `v*` tags and manual dispatch on a tag; **not** pull requests | blocks `publish` |

### Release gate: known advisories in the runtime dependencies

`runtime-dependency-audit` installs the downloaded candidate wheel (the exact artifact `publish` uploads) into a clean virtual environment, with and without `[otel]`, on Python 3.11 and 3.14 (`azure-functions` resolves to a different major on 3.11-3.12 than on 3.13-3.14, so one interpreter is not enough). Each cell runs `pip freeze --exclude azure-functions-logging`, `test -s` and `pip-audit==2.10.1 --no-deps --disable-pip --strict`, and fails on any known advisory, an empty dependency list or a package `pip-audit` cannot audit. `pip-audit` reports no severity, so every advisory blocks. The audit queries PyPI: if it is unreachable the release stays blocked until a retry passes (`gh workflow run publish-pypi.yml --ref vX.Y.Z`). Each cell uploads its JSON report (`runtime-audit-*`, 30 days).

An advisory that cannot be fixed yet may be waived for at most 90 days in `security/runtime-advisory-exceptions.txt`, one line each:

```text
ADVISORY-ID owner added expires reason...
```

`added` and `expires` are ISO dates. A waiver that is expired, not yet added, malformed or longer than 90 days fails the gate (`tools/runtime_audit_args.py`). The gate reads the file from the tagged commit, so a waiver must be on `main` before the Release PR is merged; after a failed tag, fix forward with the next release. Pull-request CI does not run the gate, so check an edit with `python tools/runtime_audit_args.py security/runtime-advisory-exceptions.txt`.
