"""Cookie/Storage audit: GDPR, 3rd party, Secure, SameSite, localStorage."""

from urllib.parse import urlparse

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, authenticated_context

logger = get_logger(__name__)

SUITE = "cookies"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Audit cookies and web storage on the base page.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    base = crawl_result.base_url
    base_domain = urlparse(base).netloc

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await authenticated_context(browser)
            page = await context.new_page()
            start = timer_ms()
            try:
                await page.goto(base, timeout=30_000, wait_until="load")
                await page.wait_for_timeout(2000)

                cookies = await context.cookies()

                third_party = [c for c in cookies if base_domain not in c.get("domain", "")]
                insecure = [c for c in cookies if not c.get("secure", False)]
                no_httponly = [c for c in cookies if not c.get("httpOnly", False)]
                no_samesite = [c for c in cookies if not c.get("sameSite")]

                results.append(TestResult(
                    test_name=f"{SUITE}:total",
                    status="pass",
                    message=f"{len(cookies)} cookie(s) found",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"count": len(cookies), "names": [c["name"] for c in cookies]},
                ))
                results.append(TestResult(
                    test_name=f"{SUITE}:third_party",
                    status="warning" if third_party else "pass",
                    message=f"{len(third_party)} third-party cookie(s)",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"third_party": [c["name"] for c in third_party]},
                ))
                results.append(TestResult(
                    test_name=f"{SUITE}:secure_flag",
                    status="fail" if insecure else "pass",
                    message=f"{len(insecure)} cookie(s) missing Secure flag" if insecure else "All cookies have Secure flag",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"insecure": [c["name"] for c in insecure]},
                ))
                results.append(TestResult(
                    test_name=f"{SUITE}:httponly_flag",
                    status="warning" if no_httponly else "pass",
                    message=f"{len(no_httponly)} cookie(s) missing HttpOnly flag" if no_httponly else "All cookies have HttpOnly flag",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"no_httponly": [c["name"] for c in no_httponly]},
                ))
                results.append(TestResult(
                    test_name=f"{SUITE}:samesite",
                    status="warning" if no_samesite else "pass",
                    message=f"{len(no_samesite)} cookie(s) missing SameSite attribute" if no_samesite else "All cookies have SameSite attribute",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"no_samesite": [c["name"] for c in no_samesite]},
                ))

                # Storage sizes
                storage_info: dict = await page.evaluate(
                    """() => {
                        let ls = 0, ss = 0;
                        try { for (let k in localStorage) ls += localStorage[k].length; } catch(e) {}
                        try { for (let k in sessionStorage) ss += sessionStorage[k].length; } catch(e) {}
                        return { localStorage_chars: ls, sessionStorage_chars: ss };
                    }"""
                )
                results.append(TestResult(
                    test_name=f"{SUITE}:storage",
                    status="pass",
                    message=f"localStorage: {storage_info['localStorage_chars']} chars, sessionStorage: {storage_info['sessionStorage_chars']} chars",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details=storage_info,
                ))

                # Cookie consent banner
                consent_visible: bool = await page.evaluate(
                    """() => {
                        const keywords = ['cookie', 'consent', 'gdpr', 'accept'];
                        return Array.from(document.querySelectorAll('*')).some(el => {
                            const text = (el.textContent || '').toLowerCase();
                            const isVisible = el.offsetWidth > 0 && el.offsetHeight > 0;
                            return isVisible && keywords.some(k => text.includes(k)) && text.length < 500;
                        });
                    }"""
                )
                results.append(TestResult(
                    test_name=f"{SUITE}:consent_banner",
                    status="pass" if consent_visible else "warning",
                    message="Cookie consent mechanism detected" if consent_visible else "No cookie consent banner found",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"has_consent_ui": consent_visible},
                ))

            except Exception as exc:
                logger.error("Cookie audit failed: %s", exc)
                results.append(TestResult(
                    test_name=f"{SUITE}:error",
                    status="fail",
                    message=f"Cookie audit error: {exc}",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details=None,
                ))
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    return results
