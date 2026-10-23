#!/bin/sh
# Resolve only existing interpreters; never create or synchronize a Hatch environment.
existing=$(hatch env find 2>/dev/null || true)
for candidate in "$existing/bin/python" "${VIRTUAL_ENV:-/nonexistent}/bin/python" .venv/bin/python python3.11 python3 python; do
    if "$candidate" -c 'import sys; assert (3, 11) <= sys.version_info[:2] < (3, 15)' 2>/dev/null; then
        printf '%s\n' "$candidate"
        exit 0
    fi
done
printf '%s\n' 'Python >=3.11,<3.15 required; run make install' >&2
exit 1
