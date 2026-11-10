# Release History and Provenance

This page records how each published version of **azure-functions-logging** maps to a Git tag, a
GitHub Release and a PyPI distribution, and lists the historical cases where those records do not
line up. The data was reconciled against Git, PyPI and GitHub on 2026-11-10. For how new versions
are released, see [Release Process](release_process.md).

---

## What each record proves

| Record | Proves | Does not prove |
|---|---|---|
| PyPI distribution | The package users install exists, with its files and upload time | Which commit built it (only PyPI attestations say so; all 35 versions have one) |
| Git tag | A commit was labelled with a version | That the tagged source is what shipped, or that anything was published |
| GitHub Release | A release page with notes exists | That a package was published |

A GitHub Release is never evidence of publication. Check the
[PyPI release history](https://pypi.org/project/azure-functions-logging/#history).

---

## Reconciliation summary

| Evidence set | Count |
|---|---:|
| Git tags | 37 |
| PyPI versions (`0.2.0` to `0.16.0`) | 35 |
| GitHub Releases | 37 |

| Category | Versions |
|---|---|
| Published, with a matching tag and GitHub Release | 32 versions: every published version except the three below |
| Published, tag exists, GitHub Release added afterwards | `0.2.0`, `0.2.1`, `0.2.2` |
| Unpublished release candidate: tag and GitHub Release, never on PyPI | `0.15.1`, `0.15.2` |

For every published version the package files on PyPI are byte-identical to the tagged commit, and
the PyPI attestation records a build from that tag at that commit (see
[How this was verified](#how-this-was-verified)).

---

## v0.15.1 and v0.15.2: unpublished release candidates

Both versions were cut on 2026-10-16 and failed the same release gate for two different reasons.
`0.15.3` followed within the hour and is the first version published after `0.15.0`.

| Time (UTC) | Event |
|---|---|
| 13:54:57 | tag `v0.15.1` (commit `a7b3a59`); Release created at 13:55:10 |
| 13:55:11 | [`Publish to PyPI` run 38911596195](https://github.com/yeongseon/azure-functions-logging-python/actions/runs/38911596195) starts and fails |
| 14:13:23 | tag `v0.15.2` (commit `6cac116`); Release created at 14:13:37 |
| 14:13:39 | [`Publish to PyPI` run 38914052967](https://github.com/yeongseon/azure-functions-logging-python/actions/runs/38914052967) starts and fails |
| 14:35:27 | tag `v0.15.3` (commit `7ac5ce6`); Release created at 14:35:39 |
| 14:40:52 | `0.15.3` uploaded to PyPI |

**Facts.** In both runs the build, library tests, cookbook dogfood smoke and real-Azure
certification succeeded. Only the *Cookbook host-boot smoke* job failed, so `publish` was skipped.
The job logs show the cause of each failure:

- **`v0.15.1`**, step *Verify logging-specific collection*. The workflow ran
  `hatch run pytest --collect-only -q -m "e2e and package_logging" tests/e2e/test_package_runtime.py`
  inside the cookbook's environment without `--no-cov`. Collecting without running any test left
  coverage at 0%, so the cookbook's threshold failed the step:
  `FAIL Required test coverage of 95.0% not reached. Total coverage: 0.00%`, exit code 1.
- **`v0.15.2`**. The collection check now passed (`1/3 tests collected (2 deselected)`), but the next
  step, *Boot cookbook func host with candidate wheel*, failed. Its `run:` value was a multi-line
  plain YAML scalar, which folds the line break into a space, so the line-continuation backslash
  reached the shell as `\ tests/e2e/test_package_runtime.py`. Pytest reported
  `file or directory not found`, collected 0 items and exited with code 4.

`v0.15.3` collects with `--no-cov` and writes the host-smoke command as a block scalar (`run: |`).
Both candidates are ancestors of `v0.15.3`, so every change in `0.15.1` and `0.15.2` shipped in
`0.15.3`. Neither failure was a product defect or a deliberate decision not to publish.

**Decision**

- The tags and Releases are kept; nothing is moved, deleted or re-uploaded. Each Release body now
  opens with a notice that the version was not published and points to `0.15.3`; the notices are
  protected statements in `.github/release-notes.json`.
- Docs and README do not claim these versions are installable: the only pin in the docs is
  `azure-functions-logging>=0.10,<1`, and `CHANGELOG.md` only lists the Release Please sections.
- **Retry criteria.** Re-running a tag is only for a transient or environmental failure. A
  `workflow_dispatch` runs the workflow file at the tag, so it cannot pick up a correction made on
  `main`. Both failures above were defects in the workflow as it stood at the tag, so a re-run
  would have failed the same way, and fixing forward, which is what shipped `0.15.3`, was the only
  path. Never move a tag or upload an altered artifact under a consumed version.

---

## GitHub Releases added for published versions

These versions were already on PyPI and already had a tag, but no GitHub Release. The Release was
added afterwards on the **existing** tag; no tag, package file or date was changed. Notes are
reconstructed from `CHANGELOG.md` and cross-checked against the commits between the tags, which
agree item for item. `0.2.0` is the first tagged version, so its Release has no compare range.

| Version | PyPI upload (UTC) | Tagged commit | PyPI attestation |
|---|---|---|---|
| `0.2.0` | 2026-03-12 | `d776dd1` | built from the tag at this commit |
| `0.2.1` | 2026-03-12 | `00b9b3e` | built from the tag at this commit |
| `0.2.2` | 2026-03-14 | `a5006b2` | built from the tag at this commit |

GitHub orders Releases by the date of their tag, so each added Release appears next to its
neighbours rather than at the top of the list; the time it was added is recorded as its
publication time. Older Release bodies link to the former repository name
`azure-functions-logging`; GitHub redirects those URLs, including compare links, to the current
repository.

---

## Checking the history automatically

`make release-audit` re-reads Git tags, GitHub Releases, `CHANGELOG.md` and PyPI and exits
non-zero for any discrepancy that is not an approved exception. It only reads: it never moves,
creates or deletes a tag, a Release or a package. Set `GH_TOKEN` to stay under GitHub's anonymous
rate limit, for example `GH_TOKEN=$(gh auth token) make release-audit`.

| Code | Meaning |
|---|---|
| `TAG_VERSION_MISMATCH` | the tagged source declares a different version than the tag |
| `TAG_NOT_ON_MAINLINE` | the tagged commit is not on the history of `main` |
| `TAG_ONLY` | a tag with neither a PyPI distribution nor a GitHub Release |
| `PYPI_WITHOUT_TAG` | published to PyPI, but no Git tag exists |
| `PYPI_WITHOUT_RELEASE` | published and tagged, but no GitHub Release exists |
| `RELEASE_WITHOUT_PYPI` | a GitHub Release exists, but nothing was published to PyPI |
| `RELEASE_WITHOUT_TAG` | a GitHub Release exists, but its tag does not |
| `CHANGELOG_MISSING` | tagged, released or published, but `CHANGELOG.md` has no section for it |

The approved exceptions are the cases documented on this page, kept in
`.github/release-audit.json` with their reason and a link to the section that explains them. An
exception must match the findings exactly, so one that no longer applies, or no longer covers
everything found for that version, fails the audit instead of going stale. A release younger than
12 hours that is still in the publish gate is reported as pending rather than as a failure. Do not
edit the file to silence a real defect: fix forward, or record the case here with its evidence.

Two narrower commands are used by the release pipeline. `python -m tools.release_audit
check-tag vX.Y.Z` checks that the tagged source declares that version, that the commit is on
`main` and that `CHANGELOG.md` has its section. `check-published vX.Y.Z --wait-minutes N` waits
until PyPI serves the version. Exit codes are 0 for clean, 1 for a discrepancy and 2 when the
audit itself could not run. The full audit also runs weekly in the `Release history audit`
workflow; see [Release verification and alerts](release_process.md#release-verification-and-alerts).

---

## How this was verified

1. **Tag, commit and version.** `git show vX.Y.Z:src/azure_functions_logging/__init__.py` gives the
   declared `__version__`, and `git merge-base --is-ancestor vX.Y.Z origin/main` tells whether the
   tag is on the history of `main`.
2. **PyPI.** The [JSON API](https://pypi.org/pypi/azure-functions-logging/json) lists each
   version's files, upload time and yanked state.
3. **PyPI files against the tagged commit.** The snippet below compares the package files in the
   sdist with the package directory at the tag, using Git blob IDs. All 35 published versions are
   identical to their tags. Run it from a clone that has the tags.
4. **PyPI attestations.** `https://pypi.org/integrity/azure-functions-logging/<version>/<sdist file>/provenance`
   returns an attestation whose certificate records the source commit and the workflow run. All 35
   versions have one, each records a build from its own tag, and the attested commit equals the
   tagged commit.
5. **Workflow runs.** The Actions API keeps run metadata, and job logs for about 90 days.

```python
import hashlib
import io
import json
import subprocess
import tarfile
import urllib.request

version, tag = "0.2.2", "v0.2.2"
meta = json.load(
    urllib.request.urlopen(f"https://pypi.org/pypi/azure-functions-logging/{version}/json")
)
sdist = next(u["url"] for u in meta["urls"] if u["packagetype"] == "sdist")


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


shipped = {}
with tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(sdist).read())) as tar:
    for member in tar.getmembers():
        _, found, name = member.name.partition("/azure_functions_logging/")
        if member.isfile() and found and "__pycache__" not in name:
            shipped[name] = blob_id(tar.extractfile(member).read())

listing = subprocess.run(
    ["git", "ls-tree", "-r", f"{tag}:src/azure_functions_logging"],
    capture_output=True,
    text=True,
    check=True,
).stdout
tagged = {line.split("\t")[1]: line.split()[2] for line in listing.splitlines()}
print(
    "identical"
    if shipped == tagged
    else sorted(k for k in shipped.keys() | tagged.keys() if shipped.get(k) != tagged.get(k))
)
```

---

## Rules for the future

- Never move or delete a tag, and never re-upload or replace a published file to repair history.
  Record the case here instead.
- Do not create a tag for a commit that did not produce the published package.
- When a GitHub Release is added for an existing tag, say so in its notes. Mark a release that was
  never published as such.
- Use PyPI, not a GitHub Release, to decide whether a version was published.
