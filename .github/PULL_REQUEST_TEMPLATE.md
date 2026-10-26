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

## Compatibility and documentation

- [ ] This change affects the public API, supported versions, or output format
- [ ] Documentation updated, or not needed because:

<!-- Version selection, tags, publication and repository labels are the
     release owner's, not yours. CHANGELOG.md is generated; write a good
     commit message instead of editing it. -->

### Breaking-change impact (only if applicable)

<!-- Complete this only when the PR title has ! or the final squash commit uses a BREAKING CHANGE: footer. Otherwise remove/leave blank. -->
- Previous supported behavior:
- New incompatible behavior:
- Affected consumers and scope (existing deployments, new/regenerated projects, versions, etc.):
- Migration or mitigation (or "none", with explanation):

<!-- Add review details for significant findings or any high-risk change defined in
     docs/review-evidence-policy.md. Avoid agent transcripts and empty risk fields. -->
