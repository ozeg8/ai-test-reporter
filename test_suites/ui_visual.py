"""UI/Visual test suite: overflow, overlapping elements, font sizes, scrollbars."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir, safe_filename, authenticated_context

logger = get_logger(__name__)

SUITE = "ui"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run UI visual checks on every discovered page.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    ss_dir = screenshots_dir()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for url in crawl_result.pages:
                context = await authenticated_context(browser, viewport={"width": 1440, "height": 900})
                page = await context.new_page()
                start = timer_ms()
                try:
                    await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

                    # Horizontal scrollbar
                    has_hscroll: bool = await page.evaluate(
                        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:horizontal_scroll",
                        status="fail" if has_hscroll else "pass",
                        message=f"{'Horizontal scrollbar detected' if has_hscroll else 'No horizontal scrollbar'} on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url},
                    ))

                    # Overflowing elements
                    overflow_count: int = await page.evaluate(
                        """() => {
                            const body = document.body;
                            const bw = body.clientWidth;
                            return Array.from(document.querySelectorAll('*')).filter(el => {
                                const r = el.getBoundingClientRect();
                                return r.right > bw + 5;
                            }).length;
                        }"""
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:overflow",
                        status="fail" if overflow_count > 0 else "pass",
                        message=f"{overflow_count} overflowing element(s) on {url}" if overflow_count else f"No overflow on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "overflow_count": overflow_count},
                    ))

                    # Minimum font size
                    small_text_count: int = await page.evaluate(
                        """() => {
                            return Array.from(document.querySelectorAll('p,span,a,li,td,th,div,h1,h2,h3,h4,h5,h6'))
                                .filter(el => {
                                    const fs = parseFloat(window.getComputedStyle(el).fontSize);
                                    return fs > 0 && fs < 12;
                                }).length;
                        }"""
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:font_size",
                        status="fail" if small_text_count > 0 else "pass",
                        message=f"{small_text_count} element(s) with font < 12px on {url}" if small_text_count else f"Font sizes OK on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "small_text_count": small_text_count},
                    ))

                    # Screenshot
                    ss_path = f"{ss_dir}/{safe_filename(url, 'ui')}.png"
                    try:
                        await page.screenshot(path=ss_path, full_page=True, timeout=15_000)
                    except Exception:
                        ss_path = None  # type: ignore[assignment]

                    results.append(TestResult(
                        test_name=f"{SUITE}:screenshot",
                        status="pass",
                        message=f"Full-page screenshot captured for {url}",
                        screenshot_path=ss_path,
                        duration_ms=elapsed_ms(start),
                        details={"url": url},
                    ))

                except Exception as exc:
                    logger.error("UI check failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"UI check error on {url}: {exc}",
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
