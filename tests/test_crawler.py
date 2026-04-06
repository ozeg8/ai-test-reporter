"""Unit tests for the crawler module."""

import pytest
from src.crawler import _normalize, _same_origin


def test_normalize_absolute_url():
    result = _normalize("https://example.com", "https://example.com/about")
    assert result == "https://example.com/about"


def test_normalize_relative_url():
    result = _normalize("https://example.com/page", "/contact")
    assert result == "https://example.com/contact"


def test_normalize_filters_anchor():
    result = _normalize("https://example.com", "#section")
    assert result is None


def test_normalize_filters_mailto():
    result = _normalize("https://example.com", "mailto:test@example.com")
    assert result is None


def test_normalize_filters_javascript():
    result = _normalize("https://example.com", "javascript:void(0)")
    assert result is None


def test_normalize_strips_fragment():
    result = _normalize("https://example.com", "/page#anchor")
    assert result == "https://example.com/page"


def test_normalize_strips_trailing_slash():
    result = _normalize("https://example.com", "/about/")
    assert result == "https://example.com/about"


def test_same_origin_true():
    assert _same_origin("https://example.com", "https://example.com/about") is True


def test_same_origin_false():
    assert _same_origin("https://example.com", "https://other.com/page") is False


def test_same_origin_relative():
    assert _same_origin("https://example.com", "/local-path") is True
