#!/usr/bin/env bash
# Classify the files changed by a pull request or push for CI job selection.
#
# Input : one changed path per line on stdin
#         (git diff --name-only --no-renames, so renames list old and new path).
# Output: key=value lines, meant to be appended to "$GITHUB_OUTPUT":
#   docs_only      every changed file is documentation
#   docs_changed   the docs build must run (docs files or docs build inputs changed)
#   full_required  the full test matrix must run (always the inverse of docs_only)
#
# Fail-safe: no files, any unknown path and any error select the full matrix.
set -euo pipefail

emit() {
  printf 'docs_only=%s\ndocs_changed=%s\nfull_required=%s\n' "$1" "$2" "$3"
}
trap 'echo "classifier error; running the full matrix" >&2; emit false true true' ERR

count=0
docs_only=true
docs_changed=false

while IFS= read -r f || [ -n "$f" ]; do
  [ -z "$f" ] && continue
  count=$((count + 1))
  case "$f" in
    # 1. Docs build inputs that are not documentation themselves: full matrix AND docs build.
    mkdocs.yml | pyproject.toml | src/* | scripts/render_mermaid.py | \
    scripts/puppeteer-config.json | tools/lint_doc_links.py | \
    .github/workflows/ci-test.yml | docs/*.py | docs/*.yml | docs/*.yaml | \
    docs/*.json | docs/*.toml | docs/*.js | docs/*.css | docs/*.html | docs/*.txt)
      docs_only=false
      docs_changed=true
      ;;
    # 2. Never docs-only: code, tests, tooling, CI and packaging. 'case' globs let '*'
    #    match '/', so 'src/*' covers nested paths. Markdown inside these trees is
    #    treated as code (tests read fixtures, packages ship READMEs).
    src/* | tests/* | examples/* | scripts/* | tools/* | benchmarks/* | infra/* | \
    .github/* | Makefile | Dockerfile* | docker-compose* | requirements*.txt | *.lock | \
    hatch.toml | tox.ini | setup.cfg | setup.py | MANIFEST.in | .pre-commit-config.yaml | \
    host.json | local.settings*.json | *.py | *.sh)
      docs_only=false
      ;;
    # 3. Documentation: Markdown and static images. Candidates for docs-only.
    *.md | docs/*.png | docs/*.jpg | docs/*.jpeg | docs/*.gif | docs/*.svg | \
    docs/*.webp | docs/*.ico)
      docs_changed=true
      ;;
    # 4. Anything unrecognised is NOT docs (fail-safe), e.g. llms*.txt, *.json, new file types.
    *)
      docs_only=false
      ;;
  esac
done

# No changed files (or an unreadable diff): never skip anything.
if [ "$count" -eq 0 ]; then
  echo "no changed files detected; running the full matrix" >&2
  emit false true true
  exit 0
fi

if [ "$docs_only" = true ]; then
  emit true true false
else
  emit false "$docs_changed" true
fi
