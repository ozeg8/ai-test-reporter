"""Responsive test suite: mobile/tablet/desktop screenshots and layout checks."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir, safe_filename, authenticated_context

logger = get_logger(__name__)

SUITE = "responsive"

VIEWPORTS = [
    {"name": "mobile", "width": 375, "height": 812},
    {"name": "tablet", "width": 768, "height": 1024},
    {"name": "desktop", "width": 1440, "height": 900},
]


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run responsive checks across mobile, tablet, and desktop viewports.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    ss_dir = screenshots_dir()
    pages = crawl_result.pages[:5]  # Limit to first 5 pages

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for url in pages:
                for vp in VIEWPORTS:
                    start = timer_ms()
                    context = await authenticated_context(
                        browser, viewport={"width": vp["width"], "height": vp["height"]}
                    )
                    page = await context.new_page()
                    try:
                        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

                        # Horizontal overflow at this viewport
                        has_overflow: bool = await page.evaluate(
                            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                        )

                        # Touch target size (mobile only)
                        small_targets = 0
                        if vp["name"] == "mobile":
                            small_targets = await page.evaluate(
                                """() => {
                                    return Array.from(document.querySelectorAll('a,button,[role=button]'))
                                        .filter(el => {
                                            const r = el.getBoundingClientRect();
                                            return r.width > 0 && r.height > 0 && (r.width < 44 || r.height < 44);
                                        }).length;
                                }"""
                            )

                        vp_name = vp["name"]
                        ss_name = f"{ss_dir}/{safe_filename(url, f'responsive_{vp_name}')}.png"
                        try:
                            await page.screenshot(path=ss_name, full_page=False, timeout=15_000)
                            ss_path = ss_name
                        except Exception:
                            ss_path = None  # type: ignore[assignment]

                        status = "fail" if has_overflow else "pass"
                        msg = f"{vp['name']} ({vp['width']}px): {'overflow detected' if has_overflow else 'OK'}"
                        if vp["name"] == "mobile" and small_targets:
                            msg += f", {small_targets} small touch target(s)"
                            status = "warning"

                        results.append(TestResult(
                            test_name=f"{SUITE}:{vp['name']}",
                            status=status,
                            message=msg,
                            screenshot_path=ss_path,
                            duration_ms=elapsed_ms(start),
                            details={
                                "url": url,
                                "viewport": vp["name"],
                                "width": vp["width"],
                                "has_overflow": has_overflow,
                                "small_touch_targets": small_targets,
                            },
                        ))

                    except Exception as exc:
                        logger.error("Responsive check %s %s: %s", vp["name"], url, exc)
                        results.append(TestResult(
                            test_name=f"{SUITE}:{vp['name']}",
                            status="fail",
                            message=f"{vp['name']} check failed for {url}: {exc}",
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
