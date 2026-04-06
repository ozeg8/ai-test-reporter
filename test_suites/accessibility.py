"""Accessibility test suite: alt text, heading hierarchy, keyboard access."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, screenshots_dir

logger = get_logger(__name__)

SUITE = "a11y"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run accessibility checks on every discovered page.

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
                context = await browser.new_context()
                page = await context.new_page()
                start = timer_ms()
                try:
                    await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

                    # Images missing alt text
                    missing_alt: int = await page.evaluate(
                        "() => Array.from(document.images).filter(i => !i.alt).length"
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:img_alt",
                        status="fail" if missing_alt else "pass",
                        message=f"{missing_alt} image(s) missing alt text on {url}" if missing_alt else f"All images have alt text on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "missing_alt": missing_alt},
                    ))

                    # Heading hierarchy
                    heading_issues: list[str] = await page.evaluate(
                        """() => {
                            const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
                            const issues = [];
                            let prev = 0;
                            for (const h of headings) {
                                const level = parseInt(h.tagName[1]);
                                if (level > prev + 1 && prev !== 0) {
                                    issues.push(`Skipped from h${prev} to h${level}`);
                                }
                                prev = level;
                            }
                            return issues;
                        }"""
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:heading_hierarchy",
                        status="fail" if heading_issues else "pass",
                        message=f"Heading issues on {url}: {', '.join(heading_issues)}" if heading_issues else f"Heading hierarchy OK on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "issues": heading_issues},
                    ))

                    # H1 count
                    h1_count: int = await page.evaluate(
                        "() => document.querySelectorAll('h1').length"
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:h1_count",
                        status="pass" if h1_count == 1 else ("warning" if h1_count == 0 else "warning"),
                        message=f"{h1_count} H1 tag(s) on {url} (expected exactly 1)",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "h1_count": h1_count},
                    ))

                    # Interactive elements without accessible names
                    unlabeled: int = await page.evaluate(
                        """() => {
                            return Array.from(document.querySelectorAll('button,a,[role=button],[role=link]'))
                                .filter(el => {
                                    const text = el.textContent.trim();
                                    const label = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title');
                                    return !text && !label;
                                }).length;
                        }"""
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:unlabeled_controls",
                        status="fail" if unlabeled else "pass",
                        message=f"{unlabeled} unlabeled interactive element(s) on {url}" if unlabeled else f"All controls labeled on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "unlabeled": unlabeled},
                    ))

                    # Language attribute
                    lang: str = await page.evaluate("() => document.documentElement.lang || ''")
                    results.append(TestResult(
                        test_name=f"{SUITE}:lang_attr",
                        status="pass" if lang else "warning",
                        message=f"lang='{lang}'" if lang else f"Missing lang attribute on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "lang": lang},
                    ))

                except Exception as exc:
                    logger.error("A11y check failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"A11y check error on {url}: {exc}",
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
