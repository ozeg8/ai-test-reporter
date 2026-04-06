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


async def authenticated_context(browser, **kwargs):
    """Create a BrowserContext and replay login session storage if credentials exist.

    Test suites call this instead of browser.new_context() directly so that
    pages opened inside the context start with the auth session already set.

    Args:
        browser: Playwright Browser instance.
        **kwargs: Forwarded to browser.new_context().

    Returns:
        BrowserContext (caller must close it).
    """
    import json as _json
    context = await browser.new_context(**kwargs)

    username = os.environ.get("AI_REPORTER_USERNAME")
    password = os.environ.get("AI_REPORTER_PASSWORD")

    if username and password:
        # Perform a quick login on a temp page to capture session storage,
        # then install it as an init-script on the context.
        from playwright.async_api import Page
        page: Page = await context.new_page()
        try:
            base_url = os.environ.get("AI_REPORTER_TARGET_URL", "")
            if base_url:
                await page.goto(base_url, timeout=30_000, wait_until="domcontentloaded")
                # Fill credentials
                user_sel = (
                    "input[type=text][name*=user], input[type=text][id*=user], "
                    "input[type=email], input[name=email], input[id=user-name], "
                    "input[autocomplete=username], input[name=username]"
                )
                u = page.locator(user_sel).first
                p = page.locator("input[type=password]").first
                if await u.count() and await p.count():
                    await u.fill(username, timeout=5_000)
                    await p.fill(password, timeout=5_000)
                    sub = page.locator(
                        "button[type=submit], input[type=submit], button#login-button, "
                        "button:has-text('Log in'), button:has-text('Login')"
                    ).first
                    if await sub.count():
                        await sub.click(timeout=10_000)
                    else:
                        await p.press("Enter")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    except Exception:
                        pass
                    ss = await page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))")
                    ls = await page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
                    if ss or ls:
                        ss_j = _json.dumps(ss)
                        ls_j = _json.dumps(ls)
                        script = f"(function(){{var ss={ss_j};var ls={ls_j};for(var k in ss)sessionStorage.setItem(k,ss[k]);for(var k in ls)localStorage.setItem(k,ls[k]);}})();"
                        await context.add_init_script(script)
        except Exception:
            pass
        finally:
            await page.close()

    return context


def auth_init_script() -> str:
    """Return a Playwright init-script that replays session/local storage for auth.

    Test suites call this and pass the result to context.add_init_script() so
    that pages opened after an auto-login stay authenticated.

    Returns:
        JavaScript string, or empty string if no credentials are set.
    """
    import json as _json
    raw = os.environ.get("AI_REPORTER_SESSION_STORAGE", "")
    if not raw:
        return ""
    try:
        ss = _json.loads(raw)
        ls = _json.loads(os.environ.get("AI_REPORTER_LOCAL_STORAGE", "{}"))
        ss_j = _json.dumps(ss)
        ls_j = _json.dumps(ls)
        return f"""(function(){{var ss={ss_j};var ls={ls_j};for(var k in ss)sessionStorage.setItem(k,ss[k]);for(var k in ls)localStorage.setItem(k,ls[k]);}})();"""
    except Exception:
        return ""


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
