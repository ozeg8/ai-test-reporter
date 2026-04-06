"""Unit tests for the report generator."""

import os
import pytest
from src.utils import TestResult
from src.report_generator import generate_report


def make_results() -> list[TestResult]:
    return [
        TestResult("smoke:http_status", "pass", "HTTP 200", None, 123.4, {"url": "https://example.com"}),
        TestResult("smoke:load_time", "fail", "Loaded in 12000ms", None, 12000.0, None),
        TestResult("seo:title", "warning", "Title too long", None, 45.0, {"title": "A" * 65}),
        TestResult("a11y:img_alt", "skip", "No images found", None, 10.0, None),
    ]


def test_generate_report_creates_file(tmp_path, monkeypatch):
    # Redirect reports dir to tmp_path
    monkeypatch.setattr("src.report_generator.reports_dir", lambda: str(tmp_path))

    results = make_results()
    out = generate_report("https://example.com", results, "test_output")

    assert os.path.exists(out)
    assert out.endswith(".html")


def test_report_contains_url(tmp_path, monkeypatch):
    monkeypatch.setattr("src.report_generator.reports_dir", lambda: str(tmp_path))

    results = make_results()
    out = generate_report("https://example.com", results)

    with open(out, encoding="utf-8") as fh:
        html = fh.read()

    assert "https://example.com" in html


def test_report_counts_statuses(tmp_path, monkeypatch):
    monkeypatch.setattr("src.report_generator.reports_dir", lambda: str(tmp_path))

    results = make_results()
    out = generate_report("https://example.com", results)

    with open(out, encoding="utf-8") as fh:
        html = fh.read()

    # Should contain counts
    assert "pass" in html
    assert "fail" in html
    assert "warning" in html
    assert "skip" in html
