"""Crawler: discovers pages and elements on the target site using Playwright."""

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Browser, Page

from src.utils import get_logger, timer_ms, elapsed_ms, is_headless

logger = get_logger(__name__)


@dataclass
class CrawlResult:
    """All discovered information about a site."""

    base_url: str
    pages: list[str] = field(default_factory=list)
    links: dict[str, list[str]] = field(default_factory=dict)  # page -> [href]
    images: dict[str, list[str]] = field(default_factory=dict)  # page -> [src]
    forms: dict[str, list[dict]] = field(default_factory=dict)  # page -> [{action, method, inputs}]
    nav_links: list[str] = field(default_factory=list)
    page_titles: dict[str, str] = field(default_factory=dict)  # page -> title
    duration_ms: float = 0.0


def _same_origin(base_url: str, href: str) -> bool:
    """Return True if href belongs to the same origin as base_url.

    Args:
        base_url: The starting URL.
        href: URL to check.

    Returns:
        True if same origin.
    """
    base = urlparse(base_url)
    target = urlparse(href)
    return target.netloc == "" or target.netloc == base.netloc


def _normalize(base_url: str, href: str) -> Optional[str]:
    """Normalize href to an absolute URL, filtering non-HTTP schemes.

    Args:
        base_url: The page URL the link was found on.
        href: Raw href value.

    Returns:
        Absolute URL string or None if not navigable.
    """
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urljoin(base_url, href).split("#")[0].rstrip("/")
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    return absolute


async def _extract_page_data(page: Page, url: str) -> dict:
    """Extract links, images, forms, title from an already-loaded page.

    Args:
        page: Playwright Page object with the URL loaded.
        url: The URL of the page.

    Returns:
        Dict with keys: links, images, forms, title.
    """
    # Links
    link_hrefs: list[str] = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    links = [h for h in link_hrefs if h]

    # Images
    img_srcs: list[str] = await page.eval_on_selector_all(
        "img[src]", "els => els.map(e => e.getAttribute('src'))"
    )
    images = [s for s in img_srcs if s]

    # Forms
    forms_data: list[dict] = await page.evaluate(
        """() => {
            return Array.from(document.querySelectorAll('form')).map(f => ({
                action: f.action || '',
                method: f.method || 'get',
                inputs: Array.from(f.querySelectorAll('input,textarea,select')).map(i => ({
                    name: i.name || '',
                    type: i.type || 'text',
                    required: i.required || false,
                })),
            }));
        }"""
    )

    # Title
    title: str = await page.title()

    return {"links": links, "images": images, "forms": forms_data, "title": title}


async def crawl(
    base_url: str,
    max_pages: int = 20,
    timeout_ms: int = 30_000,
) -> CrawlResult:
    """Crawl a website starting from base_url and discover pages and elements.

    Args:
        base_url: The starting URL to crawl.
        max_pages: Maximum number of pages to visit.
        timeout_ms: Playwright navigation timeout in milliseconds.

    Returns:
        CrawlResult with all discovered data.
    """
    start = timer_ms()
    result = CrawlResult(base_url=base_url)
    visited: set[str] = set()
    queue: list[str] = [base_url.rstrip("/")]

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=is_headless())
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; AITestReporter/1.0)"
        )

        try:
            while queue and len(visited) < max_pages:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                page = await context.new_page()
                try:
                    logger.info("Crawling: %s", url)
                    response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

                    if response and response.status >= 400:
                        logger.warning("HTTP %s for %s", response.status, url)
                        await page.close()
                        continue

                    data = await _extract_page_data(page, url)

                    result.pages.append(url)
                    result.links[url] = data["links"]
                    result.images[url] = data["images"]
                    result.forms[url] = data["forms"]
                    result.page_titles[url] = data["title"]

                    # Enqueue discovered same-origin links
                    for href in data["links"]:
                        normalized = _normalize(url, href)
                        if normalized and _same_origin(base_url, normalized) and normalized not in visited:
                            queue.append(normalized)

                except Exception as exc:
                    logger.error("Failed to crawl %s: %s", url, exc)
                finally:
                    await page.close()

            # Collect nav links from first page
            if result.pages:
                first_page_links = result.links.get(result.pages[0], [])
                result.nav_links = [
                    _normalize(result.pages[0], h)
                    for h in first_page_links
                    if _normalize(result.pages[0], h) and _same_origin(base_url, _normalize(result.pages[0], h))  # type: ignore[arg-type]
                ]
                result.nav_links = [l for l in result.nav_links if l]

        finally:
            await browser.close()

    result.duration_ms = elapsed_ms(start)
    logger.info(
        "Crawl complete: %d pages in %.0fms", len(result.pages), result.duration_ms
    )
    return result


def main() -> None:
    """CLI entry point: python -m src.crawler <url>."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.crawler <url>")
        sys.exit(1)
    url = sys.argv[1]
    result = asyncio.run(crawl(url))
    print(f"\nCrawled {len(result.pages)} pages:")
    for page in result.pages:
        title = result.page_titles.get(page, "")
        print(f"  {page}  [{title}]")


if __name__ == "__main__":
    main()
