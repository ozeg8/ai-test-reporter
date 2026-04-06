"""i18n test suite: charset, RTL detection, date/currency patterns."""

import re

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, authenticated_context

logger = get_logger(__name__)

SUITE = "i18n"

DATE_PATTERN = re.compile(r"\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b")
CURRENCY_PATTERN = re.compile(r"[\$\€\£\¥]\s*\d+|\d+\s*[\$\€\£\¥]")


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run i18n checks: charset, RTL, hardcoded dates/currencies.

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
                context = await authenticated_context(browser)
                page = await context.new_page()
                start = timer_ms()
                try:
                    await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

                    i18n_data: dict = await page.evaluate(
                        """() => {
                            const charset = (document.querySelector('meta[charset]') || {}).getAttribute?.('charset')
                                || (document.querySelector("meta[http-equiv='Content-Type']") || {}).getAttribute?.('content')
                                || document.characterSet || '';
                            const dir = document.documentElement.dir || document.body.dir || '';
                            const rtlElements = document.querySelectorAll('[dir=rtl]').length;
                            const lang = document.documentElement.lang || '';
                            const bodyText = document.body.innerText || '';
                            return { charset, dir, rtlElements, lang, bodyText: bodyText.substring(0, 2000) };
                        }"""
                    )

                    charset = i18n_data.get("charset", "").lower()
                    results.append(TestResult(
                        test_name=f"{SUITE}:charset",
                        status="pass" if "utf-8" in charset or "utf8" in charset else "warning",
                        message=f"Charset: {charset or 'not specified'} on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "charset": charset},
                    ))

                    lang = i18n_data.get("lang", "")
                    results.append(TestResult(
                        test_name=f"{SUITE}:lang",
                        status="pass" if lang else "warning",
                        message=f"lang attribute: '{lang}'" if lang else f"Missing lang attribute on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "lang": lang},
                    ))

                    rtl_els = i18n_data.get("rtlElements", 0)
                    page_dir = i18n_data.get("dir", "")
                    results.append(TestResult(
                        test_name=f"{SUITE}:rtl",
                        status="pass",
                        message=f"RTL direction: '{page_dir}', {rtl_els} RTL element(s) on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "dir": page_dir, "rtl_element_count": rtl_els},
                    ))

                    body_text = i18n_data.get("bodyText", "")
                    dates_found = DATE_PATTERN.findall(body_text)
                    currencies_found = CURRENCY_PATTERN.findall(body_text)
                    results.append(TestResult(
                        test_name=f"{SUITE}:hardcoded_formats",
                        status="warning" if (dates_found or currencies_found) else "pass",
                        message=f"Found {len(dates_found)} date(s) and {len(currencies_found)} currency pattern(s) on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={
                            "url": url,
                            "dates": dates_found[:5],
                            "currencies": currencies_found[:5],
                        },
                    ))

                except Exception as exc:
                    logger.error("i18n check failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"i18n check error on {url}: {exc}",
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
