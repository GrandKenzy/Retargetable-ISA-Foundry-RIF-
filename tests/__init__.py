"""All repository test suites live under this package."""

from __future__ import annotations

import unittest


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    """Keep the default ``vnma test`` command focused on essential tests."""

    from .test_essential_suite import load_tests as load_essential_tests

    return load_essential_tests(loader, tests, pattern)
