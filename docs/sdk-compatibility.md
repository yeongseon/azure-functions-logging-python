# Azure Functions SDK compatibility

Python runtime support and SDK support are different contracts. This package
supports Python 3.11–3.14 and requires `azure-functions>=1.21.0`.

The SDK bound is intentionally open. Required CI resolves both the exact floor
(`1.21.0`) and the newest stable release allowed by the requirement, installs
the candidate wheel, and runs import/structured-output smoke checks. The same
SDK selections run under a real local Functions host on Python 3.11 and 3.12,
including invocation context and secure redaction assertions. Pip's stable
resolver is used; prereleases are not certified implicitly.

| Configuration | Evidence boundary |
| --- | --- |
| SDK 1.21.0, Python 3.11 | Candidate-wheel install/import and output smoke |
| Latest stable SDK >=1.21.0, Python 3.11 | Forward-compatibility candidate-wheel smoke; resolved version printed in CI |
| Both SDK selections, Python 3.11/3.12, Core Tools v4 | Candidate-wheel host registration, invocation fields and redaction |
| Python 3.13/3.14 | Offline library matrix; not a claim of host certification on those interpreters |
| Future SDK majors | Not certified before the forward-compatibility lane actually passes with that major |

An open dependency bound is permission for the resolver, not a claim that every
future major has been tested. On a new-major failure, review the SDK change and
either adapt with regression tests or introduce a justified temporary ceiling
and upgrade plan. Do not silently call an untested major certified. Keep the
existing required CI and Azure release gates; local host success does not prove
Application Insights ingestion or cloud deployment compatibility.
