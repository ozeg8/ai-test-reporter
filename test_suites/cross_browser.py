"""Cross-browser test suite: smoke checks on Chromium, Firefox, WebKit."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir, safe_filename

logger = get_logger(__name__)

SUITE = "crossbrowser"

BROWSERS = ["chromium", "firefox", "webkit"]


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run smoke checks across Chromium, Firefox, and WebKit.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    ss_dir = screenshots_dir()
    pages = crawl_result.pages[:3]

    async with async_playwright() as pw:
        for browser_name in BROWSERS:
            launcher = getattr(pw, browser_name)
            try:
                browser = await launcher.launch(headless=True)
            except Exception as exc:
                results.append(TestResult(
                    test_name=f"{SUITE}:{browser_name}",
                    status="fail",
                    message=f"Could not launch {browser_name}: {exc}",
                    screenshot_path=None,
                    duration_ms=0.0,
                    details=None,
                ))
                continue

            try:
                for url in pages:
                    start = timer_ms()
                    context = await browser.new_context()
                    page = await context.new_page()
                    try:
                        resp = await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                        status = resp.status if resp else 0
                        title = await page.title()

                        ss_path = f"{ss_dir}/{safe_filename(url, f'crossbrowser_{browser_name}')}.png"
                        try:
                            await page.screenshot(path=ss_path, timeout=15_000)
                        except Exception:
                            ss_path = None  # type: ignore[assignment]

                        results.append(TestResult(
                            test_name=f"{SUITE}:{browser_name}",
                            status="pass" if status < 400 else "fail",
                            message=f"[{browser_name}] {url} → HTTP {status} | '{title}'",
                            screenshot_path=ss_path,
                            duration_ms=elapsed_ms(start),
                            details={"browser": browser_name, "url": url, "status": status},
                        ))
                    except Exception as exc:
                        results.append(TestResult(
                            test_name=f"{SUITE}:{browser_name}",
                            status="fail",
                            message=f"[{browser_name}] {url} error: {exc}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"browser": browser_name, "url": url},
                        ))
                    finally:
                        await page.close()
                        await context.close()
            finally:
                await browser.close()

    return results
