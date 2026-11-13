"""Run focused football-domain validation and the complete regression suite."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_RUNS = (
    ("Football domain contract", ROOT / "tests/test_football_models.py"),
    ("Full regression suite", ROOT / "tests"),
)


def main() -> int:
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 2

    try:
        import pytest
    except ImportError as error:
        print(
            f"pytest is required ({error}). Install it with "
            '`python -m pip install -e ".[test]"`.',
            file=sys.stderr,
        )
        return 2

    failed = False
    for label, test_path in TEST_RUNS:
        print(f"\n=== {label} ===", flush=True)
        result = pytest.main(["-q", str(test_path)], plugins=[])
        if result == pytest.ExitCode.OK:
            print(f"PASS: {label}", flush=True)
        else:
            print(f"FAIL: {label} (exit code {int(result)})", flush=True)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
