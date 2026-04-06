"""Crawler: discovers pages and elements on the target site using Playwright."""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from src.utils import get_logger, timer_ms, elapsed_ms, is_headless

logger = get_logger(__name__)


@dataclass
class CrawlResult:
    """All discovered information about a site."""

    base_url: str
    pages: list[str] = field(default_factory=list)
    links: dict[str, list[str]] = field(default_factory=dict)
    images: dict[str, list[str]] = field(default_factory=dict)
    forms: dict[str, list[dict]] = field(default_factory=dict)
    nav_links: list[str] = field(default_factory=list)
    page_titles: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    logged_in: bool = False


def _same_origin(base_url: str, href: str) -> bool:
    base = urlparse(base_url)
    target = urlparse(href)
    return target.netloc == "" or target.netloc == base.netloc


def _normalize(base_url: str, href: str) -> Optional[str]:
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urljoin(base_url, href).split("#")[0].rstrip("/")
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    return absolute


async def _extract_page_data(page: Page, url: str) -> dict:
    link_hrefs: list[str] = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    img_srcs: list[str] = await page.eval_on_selector_all(
        "img[src]", "els => els.map(e => e.getAttribute('src'))"
    )
    forms_data: list[dict] = await page.evaluate(
        """() => Array.from(document.querySelectorAll('form')).map(f => ({
            action: f.action || '',
            method: f.method || 'get',
            inputs: Array.from(f.querySelectorAll('input,textarea,select')).map(i => ({
                name: i.name || '',
                type: i.type || 'text',
                required: i.required || false,
            })),
        }))"""
    )
    title: str = await page.title()
    return {
        "links":  [h for h in link_hrefs if h],
        "images": [s for s in img_srcs if s],
        "forms":  forms_data,
        "title":  title,
    }


async def crawl(
    base_url: str,
    max_pages: int = 20,
    timeout_ms: int = 30_000,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> CrawlResult:
    username = username or os.environ.get("AI_REPORTER_USERNAME")
    password = password or os.environ.get("AI_REPORTER_PASSWORD")

    start = timer_ms()
    result = CrawlResult(base_url=base_url)
    visited: set[str] = set()

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=is_headless())
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; AITestReporter/1.0)",
            viewport={"width": 1440, "height": 900},
        )

        try:
            # Use a single persistent page so sessionStorage survives across navigations
            page = await context.new_page()

            # ── Login ──────────────────────────────────────────────────────
            if username and password:
                try:
                    await page.goto(base_url, timeout=timeout_ms, wait_until="domcontentloaded")
                    user_sel = (
                        "input[type=text][name*=user], input[type=text][id*=user], "
                        "input[type=email], input[name=email], input[id=user-name], "
                        "input[autocomplete=username], input[name=username]"
                    )
                    u = page.locator(user_sel).first
                    p = page.locator("input[type=password]").first
                    if await u.count() and await p.count():
                        await u.fill(username, timeout=5_000)
                        await p.fill(password, timeout=5_000)
                        sub = page.locator(
                            "button[type=submit], input[type=submit], "
                            "button#login-button, button:has-text('Login'), "
                            "button:has-text('Log in'), button:has-text('Sign in')"
                        ).first
                        if await sub.count():
                            await sub.click(timeout=10_000)
                        else:
                            await p.press("Enter")
                        await page.wait_for_load_state("networkidle", timeout=20_000)
                        result.logged_in = page.url.rstrip("/") != base_url.rstrip("/")
                        logger.info("Auto-login → %s (logged_in=%s)", page.url, result.logged_in)
                    else:
                        await page.goto(base_url, timeout=timeout_ms, wait_until="domcontentloaded")
                except Exception as exc:
                    logger.warning("Login attempt failed: %s", exc)
                    await page.goto(base_url, timeout=timeout_ms, wait_until="domcontentloaded")
            else:
                await page.goto(base_url, timeout=timeout_ms, wait_until="domcontentloaded")

            # ── BFS crawl on the SAME page (preserves sessionStorage) ──────
            queue: list[str] = [page.url.rstrip("/")]

            while queue and len(visited) < max_pages:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                try:
                    if page.url.rstrip("/") != url:
                        logger.info("Crawling: %s", url)
                        response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                        if response and response.status >= 400:
                            logger.warning("HTTP %s for %s", response.status, url)
                            continue
                    else:
                        logger.info("Crawling: %s (already here)", url)

                    data = await _extract_page_data(page, url)
                    result.pages.append(url)
                    result.links[url]  = data["links"]
                    result.images[url] = data["images"]
                    result.forms[url]  = data["forms"]
                    result.page_titles[url] = data["title"]

                    for href in data["links"]:
                        normalized = _normalize(url, href)
                        if normalized and _same_origin(base_url, normalized) and normalized not in visited:
                            queue.append(normalized)

                except Exception as exc:
                    logger.error("Failed to crawl %s: %s", url, exc)

            # Nav links
            if result.pages:
                first_links = result.links.get(result.pages[0], [])
                result.nav_links = [
                    n for h in first_links
                    if (n := _normalize(result.pages[0], h)) and _same_origin(base_url, n)
                ]

            await page.close()

        finally:
            await browser.close()

    result.duration_ms = elapsed_ms(start)
    logger.info("Crawl complete: %d pages in %.0fms", len(result.pages), result.duration_ms)
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.crawler <url>")
        sys.exit(1)
    result = asyncio.run(crawl(sys.argv[1]))
    print(f"\nCrawled {len(result.pages)} pages (logged_in={result.logged_in}):")
    for p in result.pages:
        print(f"  {p}  [{result.page_titles.get(p, '')}]")


if __name__ == "__main__":
    main()
