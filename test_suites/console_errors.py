"""Console/JS error scan: capture errors, warnings, unhandled rejections."""

import asyncio

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms

logger = get_logger(__name__)

SUITE = "console"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Capture console errors and unhandled rejections on each page.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for url in crawl_result.pages:
                context = await browser.new_context()
                page = await context.new_page()
                start = timer_ms()

                errors: list[str] = []
                warnings: list[str] = []
                rejections: list[str] = []

                page.on("console", lambda m: (
                    errors.append(m.text) if m.type == "error" else
                    warnings.append(m.text) if m.type == "warning" else None
                ))
                page.on("pageerror", lambda exc: rejections.append(str(exc)))

                try:
                    await page.goto(url, timeout=30_000, wait_until="load")
                    await asyncio.sleep(1)

                    results.append(TestResult(
                        test_name=f"{SUITE}:errors",
                        status="pass" if not errors else "fail",
                        message=f"{'No' if not errors else len(errors)} console error(s) on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "errors": errors[:10]},
                    ))
                    results.append(TestResult(
                        test_name=f"{SUITE}:warnings",
                        status="pass" if not warnings else "warning",
                        message=f"{'No' if not warnings else len(warnings)} console warning(s) on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "warnings": warnings[:10]},
                    ))
                    results.append(TestResult(
                        test_name=f"{SUITE}:rejections",
                        status="pass" if not rejections else "fail",
                        message=f"{'No' if not rejections else len(rejections)} unhandled rejection(s) on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "rejections": rejections[:5]},
                    ))

                except Exception as exc:
                    logger.error("Console scan failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"Console scan error on {url}: {exc}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url},
                    ))
                finally:
                    await page.close()
                    await context.close()
        finally:
            await browser.close()

    return results
