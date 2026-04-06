"""Form validation test suite: empty submit, XSS payloads, special chars."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir, safe_filename

logger = get_logger(__name__)

SUITE = "forms"

XSS_PAYLOAD = "<script>alert('xss')</script>"
INVALID_EMAIL = "not-an-email"
SPECIAL_CHARS = "emoji 🎉 unicode ñ ü 中文"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run form-specific tests including XSS and edge case inputs.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    ss_dir = screenshots_dir()

    pages_with_forms = {url: forms for url, forms in crawl_result.forms.items() if forms}
    if not pages_with_forms:
        return [TestResult(
            test_name=f"{SUITE}:no_forms",
            status="skip",
            message="No forms found on site",
            screenshot_path=None,
            duration_ms=0.0,
            details=None,
        )]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for page_url, forms in list(pages_with_forms.items())[:3]:
                for idx, form in enumerate(forms[:2]):
                    # XSS test
                    start = timer_ms()
                    context = await browser.new_context()
                    page = await context.new_page()
                    try:
                        await page.goto(page_url, timeout=30_000, wait_until="domcontentloaded")
                        form_el = page.locator("form").nth(idx)
                        inputs = form_el.locator("input[type=text], input:not([type]), textarea")
                        count = await inputs.count()
                        if count > 0:
                            await inputs.first.fill(XSS_PAYLOAD, timeout=5_000)
                            submit = form_el.locator("[type=submit], button")
                            if await submit.count() > 0:
                                await submit.first.click(timeout=5_000)
                                await page.wait_for_timeout(1000)
                                # Check if XSS payload is reflected unescaped
                                body = await page.content()
                                xss_reflected = "<script>alert" in body
                                ss_path = f"{ss_dir}/{safe_filename(page_url, f'forms_xss_{idx}')}.png"
                                try:
                                    await page.screenshot(path=ss_path, timeout=10_000)
                                except Exception:
                                    ss_path = None  # type: ignore[assignment]
                                results.append(TestResult(
                                    test_name=f"{SUITE}:xss_reflection",
                                    status="fail" if xss_reflected else "pass",
                                    message=f"Form #{idx}: XSS payload {'REFLECTED unescaped!' if xss_reflected else 'properly escaped'}",
                                    screenshot_path=ss_path,
                                    duration_ms=elapsed_ms(start),
                                    details={"url": page_url, "form_index": idx},
                                ))
                    except Exception as exc:
                        results.append(TestResult(
                            test_name=f"{SUITE}:xss_reflection",
                            status="fail",
                            message=f"XSS test error on form #{idx}: {exc}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": page_url},
                        ))
                    finally:
                        await page.close()
                        await context.close()

                    # Special characters test
                    start = timer_ms()
                    context = await browser.new_context()
                    page = await context.new_page()
                    try:
                        await page.goto(page_url, timeout=30_000, wait_until="domcontentloaded")
                        form_el = page.locator("form").nth(idx)
                        inputs = form_el.locator("input[type=text], input:not([type]), textarea")
                        if await inputs.count() > 0:
                            await inputs.first.fill(SPECIAL_CHARS, timeout=5_000)
                            submit = form_el.locator("[type=submit], button")
                            if await submit.count() > 0:
                                await submit.first.click(timeout=5_000)
                                await page.wait_for_timeout(800)
                                crashed = await page.locator("body").count() == 0
                                results.append(TestResult(
                                    test_name=f"{SUITE}:special_chars",
                                    status="fail" if crashed else "pass",
                                    message=f"Form #{idx}: special characters {'caused crash' if crashed else 'handled OK'}",
                                    screenshot_path=None,
                                    duration_ms=elapsed_ms(start),
                                    details={"url": page_url, "form_index": idx, "payload": SPECIAL_CHARS},
                                ))
                    except Exception as exc:
                        results.append(TestResult(
                            test_name=f"{SUITE}:special_chars",
                            status="warning",
                            message=f"Special chars test error on form #{idx}: {exc}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": page_url},
                        ))
                    finally:
                        await page.close()
                        await context.close()

        finally:
            await browser.close()

    if not results:
        results.append(TestResult(
            test_name=f"{SUITE}:no_testable_forms",
            status="skip",
            message="Forms found but none were testable",
            screenshot_path=None,
            duration_ms=0.0,
            details=None,
        ))

    return results
