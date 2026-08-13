# Security

This document covers the security policy, threat model, and vulnerability reporting process for `azure-functions-logging`.

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it responsibly.

### Preferred Method

Use GitHub's private vulnerability reporting feature:

[Report a vulnerability](https://github.com/yeongseon/azure-functions-logging/security/advisories/new)

### Alternative Method

Email the maintainer: `yeongseon.choe@gmail.com`

### What to Include

- A clear description of the vulnerability
- Steps to reproduce the issue
- Assessment of potential impact
- Suggested fix or mitigation, if available

### Do Not

- Open a public GitHub issue with vulnerability details
- Share vulnerability details publicly before a fix is released
- Exploit the vulnerability against production systems

## Response Timeline

- **Initial response**: Within 48 hours of receiving your report
- **Status update**: Within 7 days
- **Ongoing updates**: Until a fix or resolution is implemented

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.2.x | Yes |
| 0.1.x | No |

Security fixes are applied to the latest release only. Users should upgrade to the latest version.

## Threat Model

`azure-functions-logging` is a logging configuration library that runs within the same process as the Azure Functions host. Its security surface is limited by design.

### File System Access

**What the library reads**:

- `host.json` -- to detect log level conflicts (read-only, catches all I/O errors)
- No other files are read at runtime

**What the library writes**:

- Log output to `stdout`/`stderr` via Python's standard logging handlers
- No files are written

### Network Access

The library makes **no network calls**. All functionality is local to the process.

### Data Handling

The library processes log messages that may contain sensitive data (request parameters, user IDs, etc.). It does not:

- Store log messages beyond the standard logging handler output
- Send log data to external services
- Cache or persist any data
- Modify log message content

Log output goes to the standard Python logging handlers, which in Azure Functions are captured by the Functions host. Data handling beyond that point is the responsibility of the Azure Functions runtime and any configured log sinks.

### Context Fields

`inject_context()` extracts the following fields from the Azure Functions context object:

- `invocation_id` -- Azure-generated UUID for the invocation
- `function_name` -- name of the Azure Function
- `trace_id` -- distributed tracing identifier (from the W3C `traceparent` header)
- `span_id` -- parent span identifier (from the W3C `traceparent` header)

Additionally, `host_instance_id` is resolved separately by the formatter/filter (not from the context object) and attached to log records.

These fields are attached to log records. They do not contain user data or secrets, but they are included in log output. Ensure your log sinks handle these fields according to your data retention policies.

### Dependencies

This package has **zero runtime dependencies**. It uses only the Python standard library (`logging`, `json`, `contextvars`, `os`).

Development dependencies (not installed at runtime):

| Package | Purpose |
| ------- | ------- |
| pytest | Test runner |
| mypy | Type checking |
| ruff | Code formatting + linting |
| bandit | Security scanning |

### Supply Chain

- The package is published to PyPI with version pinning
- CI runs `bandit` security scanning on every pull request
- Type checking via `mypy` in strict mode helps prevent type-related vulnerabilities
- Pre-commit hooks enforce code quality checks before every commit

## Best Practices

### For users of this library

- **Log sanitization**: Do not log sensitive data (passwords, API keys, tokens) directly. The library does not filter or redact log content.
- **host.json**: Configure `host.json` log levels appropriately for your environment. The library warns about conflicts but cannot override Azure's host-level configuration.
- **Version pinning**: Pin the package version in your `requirements.txt` or `pyproject.toml` to avoid unexpected behavior from new releases.
- **Context data**: Be aware that `inject_context()` fields (invocation_id, function_name, trace_id, span_id) plus the separately-resolved host_instance_id are included in log output. Configure log sinks and retention policies accordingly.

### For contributors

- Do not add external runtime dependencies
- Do not add network calls to the library
- Do not store or cache log data
- Run `make security` (bandit) before submitting pull requests
- Follow the principle of least privilege in all file and resource access
- Validate and sanitize any input from external sources (host.json content)

## Python Version Policy

`azure-functions-logging` requires Python >= 3.10. This ensures:

- Active CPython support with security patches
- `contextvars` support for async-safe context propagation
- Type annotation features (`str | None` union syntax)
- Match statement support (Python 3.10+)

Older Python versions are not supported and may contain known vulnerabilities.

## License

MIT License. See the [LICENSE](https://github.com/yeongseon/azure-functions-logging/blob/main/LICENSE) file for details.
