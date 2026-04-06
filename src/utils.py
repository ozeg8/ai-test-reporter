"""Helpers: logging, file operations, timing."""

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TestResult:
    """Standardized result returned by every test suite."""

    test_name: str
    status: str  # "pass", "fail", "warning", "skip"
    message: str
    screenshot_path: Optional[str]
    duration_ms: float
    details: Optional[dict]


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name.

    Args:
        name: Module or component name for the logger.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def safe_filename(url: str, prefix: str = "", max_len: int = 80) -> str:
    """Convert a URL to a safe filename segment.

    Args:
        url: URL string to sanitize.
        prefix: Optional prefix (e.g. suite name).
        max_len: Maximum length for the URL portion.

    Returns:
        Safe filename string without extension.
    """
    safe = re.sub(r'[\\/:*?"<>|&=%#+]', '_', url)
    safe = re.sub(r'_+', '_', safe).strip('_')[:max_len]
    return f"{prefix}_{safe}" if prefix else safe


def is_headless() -> bool:
    """Return False when the AI_REPORTER_HEADED env var is set to '1'.

    Returns:
        True for headless mode (default), False for headed/visible mode.
    """
    return os.environ.get("AI_REPORTER_HEADED", "0") != "1"


def ensure_dirs(*paths: str) -> None:
    """Create directories if they don't exist.

    Args:
        *paths: Directory paths to create.
    """
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def timer_ms() -> float:
    """Return current monotonic time in milliseconds.

    Returns:
        Current time as float milliseconds.
    """
    return time.monotonic() * 1000


def elapsed_ms(start: float) -> float:
    """Compute elapsed milliseconds since start.

    Args:
        start: Start time from timer_ms().

    Returns:
        Elapsed time in milliseconds.
    """
    return timer_ms() - start


def screenshots_dir() -> str:
    """Return absolute path to the run-specific screenshots directory.

    Uses AI_REPORTER_RUN_ID env var (set by test_runner) to create an
    isolated subdirectory per run so previous results are never overwritten.

    Returns:
        Absolute path string.
    """
    run_id = os.environ.get("AI_REPORTER_RUN_ID", "default")
    base = Path(__file__).resolve().parent.parent / "screenshots" / run_id
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def reports_dir() -> str:
    """Return absolute path to the run-specific reports directory.

    Uses AI_REPORTER_RUN_ID env var to create an isolated subdirectory
    per run so previous reports are never overwritten.

    Returns:
        Absolute path string.
    """
    run_id = os.environ.get("AI_REPORTER_RUN_ID", "default")
    base = Path(__file__).resolve().parent.parent / "reports" / run_id
    base.mkdir(parents=True, exist_ok=True)
    return str(base)
