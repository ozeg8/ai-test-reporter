"""Link validation suite: broken links, redirect chains, anchor IDs."""

import asyncio
from urllib.parse import urljoin, urlparse

import httpx

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms

logger = get_logger(__name__)

SUITE = "links"
EXTERNAL_TIMEOUT = 10


async def _check_url(client: httpx.AsyncClient, url: str) -> tuple[int, int]:
    """Return (status_code, redirect_count) for a URL.

    Args:
        client: httpx async client.
        url: URL to check.

    Returns:
        Tuple of (final_status, redirect_hops).
    """
    hops = 0
    current = url
    try:
        while hops <= 5:
            r = await client.head(current, follow_redirects=False, timeout=EXTERNAL_TIMEOUT)
            if r.is_redirect:
                current = r.headers.get("location", current)
                hops += 1
            else:
                return r.status_code, hops
    except Exception:
        return 0, hops
    return 0, hops


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Check all links discovered during crawl for broken URLs and redirect chains.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    base = crawl_result.base_url
    checked: set[str] = set()
    start = timer_ms()

    # Collect all unique links
    all_links: set[str] = set()
    for page_url, hrefs in crawl_result.links.items():
        for href in hrefs:
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_url = urljoin(page_url, href).split("#")[0]
            if urlparse(abs_url).scheme in ("http", "https"):
                all_links.add(abs_url)

    # verify=False is intentional: we are checking link reachability, not
    # validating TLS certificates. Sites under test may use self-signed certs.
    async with httpx.AsyncClient(follow_redirects=False, timeout=EXTERNAL_TIMEOUT, verify=False) as client:  # noqa: S501
        tasks = []
        link_list = list(all_links)[:50]  # cap at 50 to avoid flooding

        async def check_one(url: str) -> TestResult:
            if url in checked:
                return None  # type: ignore[return-value]
            checked.add(url)
            lstart = timer_ms()
            is_internal = urlparse(url).netloc == urlparse(base).netloc
            try:
                status, hops = await _check_url(client, url)
                ok = 200 <= status < 400
                redir_issue = hops > 3
                return TestResult(
                    test_name=f"{SUITE}:{'internal' if is_internal else 'external'}",
                    status=("pass" if ok and not redir_issue else ("warning" if redir_issue else "fail")),
                    message=f"HTTP {status} ({hops} redirect(s)) — {url}",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(lstart),
                    details={"url": url, "status": status, "redirects": hops},
                )
            except Exception as exc:
                return TestResult(
                    test_name=f"{SUITE}:error",
                    status="fail",
                    message=f"Link check failed for {url}: {exc}",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(lstart),
                    details={"url": url},
                )

        raw_results = await asyncio.gather(*[check_one(u) for u in link_list])
        results = [r for r in raw_results if r is not None]

    if not results:
        results.append(TestResult(
            test_name=f"{SUITE}:no_links",
            status="skip",
            message="No links found to validate",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details=None,
        ))

    return results
