"""Unit tests for the test runner module."""

import pytest
from src.test_runner import SUITE_MAP


def test_suite_map_has_all_suites():
    expected = {
        "smoke", "functional", "ui", "responsive", "a11y", "performance",
        "seo", "security", "links", "console", "forms", "crossbrowser",
        "api", "cookies", "assets", "i18n",
    }
    assert expected == set(SUITE_MAP.keys())


def test_suite_map_module_paths_are_strings():
    for key, module_path in SUITE_MAP.items():
        assert isinstance(module_path, str), f"Module path for {key} must be a string"
        assert module_path.startswith("test_suites."), f"Module path for {key} must start with 'test_suites.'"


def test_all_suite_modules_importable():
    import importlib
    for key, module_path in SUITE_MAP.items():
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "run"), f"Suite {key} ({module_path}) must have a 'run' function"
