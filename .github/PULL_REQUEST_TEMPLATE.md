<!-- Title: `type: description` or `type(scope): description`. See "Title Convention" in CONTRIBUTING.md. Link issues in the body (Closes #123), not in the title. -->

## Related Issue

Closes #

<!-- Required for human-authored changes. Open an issue first if one does
     not exist; a pull request without a linked issue is rejected at review.
     Automated dependency pull requests are exempt: they are opened without
     an issue and do not use this template. -->

## Summary

## Changes

## Verification

<!-- Record what you actually ran, so a reviewer can tell verified from
     assumed. -->

| Command | Environment | Result |
| --- | --- | --- |
| `make check-all` |  |  |
| `make build` |  |  |

<!-- `check-all` does not build the distribution, so it can pass while the
     packaged artifact is broken. Run `make build` as well. -->

## Not run

<!-- Checks you did not run, and why. Leave this honest rather than empty. -->

## Review Evidence

<!-- See docs/review-evidence-policy.md (advisory, not a required check).
     Record review source/SHA so evidence can be checked against the
     commit it actually evaluated, not just the PR as a whole. -->

- Review source and reviewed commit SHA:
- Material findings and disposition (fixed / acknowledged-wont-fix / deferred-with-issue), or "none":
- Unresolved blockers, or "none":
- R3 (workflow permissions, release/publishing, security-sensitive redaction/exposure, telemetry trust boundaries, review-policy files): yes/no — if yes, human authorization record:

## Compatibility and documentation

- [ ] This change affects the public API, supported versions, or output format
- [ ] Breaking change (describe the migration)
- [ ] Documentation updated, or not needed because:

<!-- Version selection, tags, publication and repository labels are the
     release owner's, not yours. CHANGELOG.md is generated; write a good
     commit message instead of editing it. -->
