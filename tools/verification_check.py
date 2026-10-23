"""Run every quality prerequisite inside the shared check evidence capture."""

import subprocess


def main() -> int:
    return subprocess.call(["make", "check-steps"])


if __name__ == "__main__":
    raise SystemExit(main())
