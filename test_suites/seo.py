"""SEO test suite: meta tags, headings, robots.txt, sitemap, Open Graph."""

import httpx
from playwright.async_api import async_playwright
from urllib.parse import urljoin

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, authenticated_context

logger = get_logger(__name__)

SUITE = "seo"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run SEO checks on every discovered page plus site-level checks.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    base = crawl_result.base_url

    # Site-level checks (robots.txt, sitemap)
    start = timer_ms()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            robots_url = urljoin(base, "/robots.txt")
            r = await client.get(robots_url)
            results.append(TestResult(
                test_name=f"{SUITE}:robots_txt",
                status="pass" if r.status_code == 200 else "warning",
                message=f"robots.txt HTTP {r.status_code}",
                screenshot_path=None,
                duration_ms=elapsed_ms(start),
                details={"url": robots_url, "status": r.status_code},
            ))

            sitemap_url = urljoin(base, "/sitemap.xml")
            s = await client.get(sitemap_url)
            results.append(TestResult(
                test_name=f"{SUITE}:sitemap",
                status="pass" if s.status_code == 200 else "warning",
                message=f"sitemap.xml HTTP {s.status_code}",
                screenshot_path=None,
                duration_ms=elapsed_ms(start),
                details={"url": sitemap_url, "status": s.status_code},
            ))
    except Exception as exc:
        logger.error("Site-level SEO checks failed: %s", exc)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for url in crawl_result.pages:
                context = await authenticated_context(browser)
                page = await context.new_page()
                start = timer_ms()
                try:
                    await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

                    seo_data: dict = await page.evaluate(
                        """() => {
                            const getMeta = (name) => {
                                const el = document.querySelector(`meta[name='${name}'], meta[property='${name}']`);
                                return el ? el.getAttribute('content') : null;
                            };
                            const title = document.title || '';
                            const desc = getMeta('description');
                            const canonical = (document.querySelector("link[rel='canonical']") || {}).href || null;
                            const ogTitle = getMeta('og:title');
                            const ogDesc = getMeta('og:description');
                            const ogImage = getMeta('og:image');
                            const h1s = Array.from(document.querySelectorAll('h1')).map(h => h.textContent.trim());
                            return { title, desc, canonical, ogTitle, ogDesc, ogImage, h1s };
                        }"""
                    )

                    title = seo_data["title"]
                    desc = seo_data["desc"]
                    h1s = seo_data["h1s"]

                    # Title
                    if not title:
                        results.append(TestResult(
                            test_name=f"{SUITE}:title",
                            status="fail",
                            message=f"Missing title on {url}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": url},
                        ))
                    else:
                        results.append(TestResult(
                            test_name=f"{SUITE}:title",
                            status="pass" if len(title) <= 60 else "warning",
                            message=f"Title ({len(title)} chars): '{title[:60]}{'...' if len(title) > 60 else ''}'",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": url, "title": title, "length": len(title)},
                        ))

                    # Meta description
                    if not desc:
                        results.append(TestResult(
                            test_name=f"{SUITE}:meta_description",
                            status="warning",
                            message=f"Missing meta description on {url}",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": url},
                        ))
                    else:
                        results.append(TestResult(
                            test_name=f"{SUITE}:meta_description",
                            status="pass" if len(desc) <= 160 else "warning",
                            message=f"Meta description ({len(desc)} chars)",
                            screenshot_path=None,
                            duration_ms=elapsed_ms(start),
                            details={"url": url, "length": len(desc)},
                        ))

                    # H1
                    results.append(TestResult(
                        test_name=f"{SUITE}:h1",
                        status="pass" if len(h1s) == 1 else "warning",
                        message=f"{len(h1s)} H1 tag(s) on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "h1s": h1s},
                    ))

                    # Open Graph
                    og_ok = bool(seo_data["ogTitle"] and seo_data["ogDesc"])
                    results.append(TestResult(
                        test_name=f"{SUITE}:open_graph",
                        status="pass" if og_ok else "warning",
                        message=f"Open Graph {'present' if og_ok else 'missing'} on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "og_title": seo_data["ogTitle"], "og_desc": seo_data["ogDesc"]},
                    ))

                    # Canonical
                    results.append(TestResult(
                        test_name=f"{SUITE}:canonical",
                        status="pass" if seo_data["canonical"] else "warning",
                        message=f"Canonical {'present' if seo_data['canonical'] else 'missing'} on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "canonical": seo_data["canonical"]},
                    ))

                except Exception as exc:
                    logger.error("SEO check failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"SEO check error on {url}: {exc}",
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
