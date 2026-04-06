"""Smoke test suite: basic health checks for every discovered page."""

import asyncio
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page, Response

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir, is_headless, safe_filename, authenticated_context

logger = get_logger(__name__)

SUITE = "smoke"


async def _check_page(
    browser: Browser,
    url: str,
    images: list[str],
    ss_dir: str,
) -> list[TestResult]:
    """Run smoke checks on a single page.

    Args:
        browser: Playwright Browser instance.
        url: Page URL.
        images: Image srcs discovered by crawler.
        ss_dir: Screenshot directory path.

    Returns:
        List of TestResult for this page.
    """
    results: list[TestResult] = []
    context = await authenticated_context(browser)
    page = await context.new_page()
    console_errors: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    start = timer_ms()
    screenshot_path: Optional[str] = None

    try:
        response: Optional[Response] = await page.goto(url, timeout=30_000, wait_until="load")
        load_ms = elapsed_ms(start)

        # HTTP status
        status_code = response.status if response else 0
        results.append(TestResult(
            test_name=f"{SUITE}:http_status",
            status="pass" if status_code == 200 else "fail",
            message=f"HTTP {status_code} for {url}",
            screenshot_path=None,
            duration_ms=load_ms,
            details={"url": url, "status_code": status_code},
        ))

        # Page load time
        results.append(TestResult(
            test_name=f"{SUITE}:load_time",
            status="pass" if load_ms < 10_000 else "fail",
            message=f"Page loaded in {load_ms:.0f}ms (limit: 10000ms)",
            screenshot_path=None,
            duration_ms=load_ms,
            details={"url": url, "load_ms": load_ms},
        ))

        # Title
        title = await page.title()
        results.append(TestResult(
            test_name=f"{SUITE}:title",
            status="pass" if title else "fail",
            message=f"Title: '{title}'" if title else "No title tag found",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details={"url": url, "title": title},
        ))

        # Favicon
        favicon_exists: bool = await page.evaluate(
            """() => {
                const link = document.querySelector("link[rel*='icon']");
                return !!link;
            }"""
        )
        results.append(TestResult(
            test_name=f"{SUITE}:favicon",
            status="pass" if favicon_exists else "warning",
            message="Favicon link found" if favicon_exists else "No favicon link tag",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details={"url": url},
        ))

        # Console errors
        await asyncio.sleep(0.5)  # let late errors surface
        results.append(TestResult(
            test_name=f"{SUITE}:console_errors",
            status="pass" if not console_errors else "fail",
            message=f"No console errors" if not console_errors else f"{len(console_errors)} console error(s)",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details={"url": url, "errors": console_errors[:10]},
        ))

        # Broken images
        broken: list[str] = await page.evaluate(
            """() => {
                return Array.from(document.images)
                    .filter(img => !img.complete || img.naturalWidth === 0)
                    .map(img => img.src);
            }"""
        )
        results.append(TestResult(
            test_name=f"{SUITE}:images",
            status="pass" if not broken else "fail",
            message="All images loaded" if not broken else f"{len(broken)} broken image(s)",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details={"url": url, "broken_images": broken[:10]},
        ))

        # Screenshot
        ss_path = f"{ss_dir}/{safe_filename(url, 'smoke')}.png"
        try:
            await page.screenshot(path=ss_path, full_page=False, timeout=10_000)
            screenshot_path = ss_path
        except Exception as exc:
            logger.warning("Screenshot failed for %s: %s", url, exc)

        # Attach screenshot to load_time result
        results[1] = TestResult(
            test_name=results[1].test_name,
            status=results[1].status,
            message=results[1].message,
            screenshot_path=screenshot_path,
            duration_ms=results[1].duration_ms,
            details=results[1].details,
        )

    except Exception as exc:
        logger.error("Smoke check failed for %s: %s", url, exc)
        results.append(TestResult(
            test_name=f"{SUITE}:page_error",
            status="fail",
            message=f"Could not load page: {exc}",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details={"url": url},
        ))
    finally:
        await page.close()
        await context.close()

    return results


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run smoke tests against all discovered pages.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    ss_dir = screenshots_dir()
    all_results: list[TestResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=is_headless())
        try:
            for url in crawl_result.pages:
                images = crawl_result.images.get(url, [])
                page_results = await _check_page(browser, url, images, ss_dir)
                all_results.extend(page_results)
        finally:
            await browser.close()

    return all_results
