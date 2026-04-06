"""Functional test suite: forms, navigation flows, and button actions."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir, safe_filename

logger = get_logger(__name__)

SUITE = "functional"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run functional tests: navigation links and form submission checks.

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
            context = await browser.new_context()

            # 1. Navigation links reachable
            nav_links = crawl_result.nav_links[:10]
            if not nav_links:
                results.append(TestResult(
                    test_name=f"{SUITE}:navigation",
                    status="skip",
                    message="No navigation links found to test",
                    screenshot_path=None,
                    duration_ms=0.0,
                    details=None,
                ))
            else:
                for link in nav_links:
                    start = timer_ms()
                    page = await context.new_page()
                    try:
                        resp = await page.goto(link, timeout=30_000, wait_until="domcontentloaded")
                        status = resp.status if resp else 0
                        results.append(TestResult(
                            test_name=f"{SUITE}:navigation",
                            status="pass" if status < 400 else "fail",
                            message=f"Nav link {link} → HTTP {status}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": link, "status": status},
                        ))
                    except Exception as exc:
                        results.append(TestResult(
                            test_name=f"{SUITE}:navigation",
                            status="fail",
                            message=f"Nav link {link} failed: {exc}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": link},
                        ))
                    finally:
                        await page.close()

            # 2. Form submission (empty submission — check for validation feedback)
            for page_url, forms in crawl_result.forms.items():
                if not forms:
                    continue
                for idx, form in enumerate(forms[:3]):
                    start = timer_ms()
                    page = await context.new_page()
                    try:
                        await page.goto(page_url, timeout=30_000, wait_until="domcontentloaded")
                        form_locator = page.locator("form").nth(idx)
                        submit = form_locator.locator("[type=submit], button[type=submit], button:not([type])")
                        count = await submit.count()
                        if count == 0:
                            results.append(TestResult(
                                test_name=f"{SUITE}:form_submit",
                                status="skip",
                                message=f"Form #{idx} on {page_url} has no submit button",
                                screenshot_path=None,
                                duration_ms=elapsed_ms(start),
                                details={"url": page_url, "form_index": idx},
                            ))
                            continue

                        await submit.first.click(timeout=10_000)
                        await page.wait_for_timeout(1000)

                        # Check if validation errors appeared or page navigated
                        error_visible = await page.locator(
                            "[aria-invalid=true], .error, .invalid, [class*='error']"
                        ).count()
                        ss_path = f"{ss_dir}/{safe_filename(page_url, f'functional_form_{idx}')}.png"
                        try:
                            await page.screenshot(path=ss_path, timeout=10_000)
                        except Exception:
                            ss_path = None  # type: ignore[assignment]

                        results.append(TestResult(
                            test_name=f"{SUITE}:form_submit",
                            status="pass" if error_visible > 0 else "warning",
                            message=f"Form #{idx}: {'validation errors shown' if error_visible else 'no validation feedback detected'}",
                            screenshot_path=ss_path,
                            duration_ms=elapsed_ms(start),
                            details={"url": page_url, "form_index": idx, "error_elements": error_visible},
                        ))
                    except Exception as exc:
                        results.append(TestResult(
                            test_name=f"{SUITE}:form_submit",
                            status="fail",
                            message=f"Form #{idx} on {page_url} error: {exc}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": page_url, "form_index": idx},
                        ))
                    finally:
                        await page.close()

            await context.close()
        finally:
            await browser.close()

    if not results:
        results.append(TestResult(
            test_name=f"{SUITE}:no_tests",
            status="skip",
            message="No functional tests applicable",
            screenshot_path=None,
            duration_ms=0.0,
            details=None,
        ))

    return results
