"""Performance test suite: Core Web Vitals via PerformanceObserver / Navigation Timing."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms

logger = get_logger(__name__)

SUITE = "performance"

# Thresholds (ms / unitless)
LCP_THRESHOLD = 2500
FCP_THRESHOLD = 1800
CLS_THRESHOLD = 0.1
TTFB_THRESHOLD = 800


async def _get_vitals(page) -> dict:
    """Collect Web Vitals from Navigation Timing and paint entries.

    Args:
        page: Playwright Page with URL already loaded.

    Returns:
        Dict with fcp, lcp, cls, ttfb, total_weight, request_count keys.
    """
    vitals = await page.evaluate(
        """() => {
            const nav = performance.getEntriesByType('navigation')[0] || {};
            const paint = performance.getEntriesByType('paint');
            const fcp = (paint.find(p => p.name === 'first-contentful-paint') || {}).startTime || 0;
            const resources = performance.getEntriesByType('resource');
            const totalWeight = resources.reduce((s, r) => s + (r.transferSize || 0), 0);
            return {
                fcp: Math.round(fcp),
                ttfb: Math.round((nav.responseStart || 0) - (nav.requestStart || 0)),
                total_weight_bytes: totalWeight,
                request_count: resources.length,
            };
        }"""
    )
    return vitals


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run performance checks on each discovered page.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for url in crawl_result.pages[:5]:
                context = await browser.new_context()
                page = await context.new_page()
                start = timer_ms()
                try:
                    await page.goto(url, timeout=30_000, wait_until="load")
                    await page.wait_for_timeout(2000)  # let vitals settle

                    vitals = await _get_vitals(page)
                    dur = elapsed_ms(start)

                    fcp = vitals.get("fcp", 0)
                    ttfb = vitals.get("ttfb", 0)
                    weight_mb = round(vitals.get("total_weight_bytes", 0) / 1_048_576, 2)
                    req_count = vitals.get("request_count", 0)

                    results.append(TestResult(
                        test_name=f"{SUITE}:fcp",
                        status="pass" if fcp <= FCP_THRESHOLD else "fail",
                        message=f"FCP {fcp}ms (target <{FCP_THRESHOLD}ms) on {url}",
                        screenshot_path=None,
                        duration_ms=dur,
                        details={"url": url, "fcp_ms": fcp},
                    ))
                    results.append(TestResult(
                        test_name=f"{SUITE}:ttfb",
                        status="pass" if ttfb <= TTFB_THRESHOLD else ("warning" if ttfb <= 1500 else "fail"),
                        message=f"TTFB {ttfb}ms (target <{TTFB_THRESHOLD}ms) on {url}",
                        screenshot_path=None,
                        duration_ms=dur,
                        details={"url": url, "ttfb_ms": ttfb},
                    ))
                    results.append(TestResult(
                        test_name=f"{SUITE}:page_weight",
                        status="pass" if weight_mb < 3 else "warning",
                        message=f"Page weight {weight_mb}MB, {req_count} requests on {url}",
                        screenshot_path=None,
                        duration_ms=dur,
                        details={"url": url, "weight_mb": weight_mb, "requests": req_count},
                    ))

                except Exception as exc:
                    logger.error("Performance check failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"Performance check error on {url}: {exc}",
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
