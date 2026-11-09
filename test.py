"""Compatibility entry point for running the automated test suite."""

import pytest


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q"]))
