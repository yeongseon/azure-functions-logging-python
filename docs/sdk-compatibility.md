# Azure Functions SDK compatibility

Python runtime support and SDK support are different contracts. This package
supports Python 3.11–3.14. Its single runtime dependency is bound by
interpreter, matching the other packages in the toolkit:

- Python 3.11/3.12: `azure-functions>=1.21.0,<2.0.0`
- Python 3.13/3.14: `azure-functions>=1.21.0,<3.0.0`

This split follows [#646](https://github.com/yeongseon/azure-functions-logging-python/issues/646):
the original unbounded `azure-functions>=1.21.0` let a future major resolve
silently, and the fix is package metadata and policy-test alignment, not
evidence that today's SDK is broken. Published stable 2.x releases require
Python >=3.13 and pip already respects that, so the `<2.0.0` cap on older
interpreters restates an existing boundary explicitly rather than fixing
today's resolution; the cap that does real work is `<3.0.0`, which prevents
future untested majors. On 3.13/3.14 the 2.x line is permitted by the
metadata, but this repository does not yet have a wheel or host lane that runs
against 2.x, so the allowance is not a claim that 2.x is certified here.
Neither marker permits an `azure-functions` 3.x release.

The 1.x bound is exercised in required CI: both the exact floor (`1.21.0`) and
the newest stable 1.x release allowed by the requirement are installed against
the candidate wheel and run import/structured-output smoke checks. The same
SDK selections run under a real local Functions host on Python 3.11 and 3.12,
including invocation context and secure redaction assertions. Pip's stable
resolver is used; prereleases are not certified implicitly.

| Configuration | Evidence boundary |
| --- | --- |
| SDK 1.21.0, Python 3.11 | Candidate-wheel install/import and output smoke |
| Latest 1.x SDK (>=1.21.0,<2.0.0), Python 3.11 | Forward-compatibility candidate-wheel smoke; resolved version printed in CI |
| Both 1.x SDK selections, Python 3.11/3.12, Core Tools v4 | Candidate-wheel host registration, invocation fields and redaction |
| Python 3.13/3.14 | Offline library matrix; 2.x is permitted by the markers but no wheel-based 2.x lane has run, so this is not a claim of host certification |
| Future SDK 3.x | Never resolved: both markers cap below 3.0.0 |

Recorded fresh-install resolutions (candidate wheel built from this branch):
Python 3.11 resolves `azure-functions` 1.25.0 (latest 1.x) with a clean
`pip check`; Python 3.14 — the same `python_version >= '3.13'` marker branch as
3.13 — resolves `azure-functions` 2.3.0 with a clean `pip check`. These are
resolver outcomes, not host certification: no 2.x host lane has run.

A dependency bound is permission for the resolver, not a claim that the newest
allowed release has been tested. If the 2.x allowance is kept, add a wheel-based
2.x lane on Python 3.13/3.14 (and record its result here) before treating it as
supported. On any new-minor failure within 1.x, review the SDK change and either
adapt with regression tests or introduce a justified temporary ceiling and
upgrade plan. Do not silently call an untested release certified. Keep the
existing required CI and Azure release gates; local host success does not prove
Application Insights ingestion or cloud deployment compatibility.
