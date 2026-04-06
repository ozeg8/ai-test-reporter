"""Asset check suite: render-blocking resources, large images, compression."""

from playwright.async_api import async_playwright

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms, authenticated_context

logger = get_logger(__name__)

SUITE = "assets"

LARGE_IMAGE_THRESHOLD_BYTES = 500_000


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Check assets for optimization issues on each page.

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

                resource_sizes: dict[str, int] = {}

                async def on_response(resp) -> None:
                    try:
                        body = await resp.body()
                        resource_sizes[resp.url] = len(body)
                    except Exception:
                        pass

                page.on("response", on_response)

                try:
                    await page.goto(url, timeout=30_000, wait_until="networkidle")

                    # Render-blocking scripts in <head>
                    blocking_scripts: int = await page.evaluate(
                        """() => {
                            const head = document.head;
                            return Array.from(head.querySelectorAll('script:not([async]):not([defer])')).length;
                        }"""
                    )
                    results.append(TestResult(
                        test_name=f"{SUITE}:render_blocking",
                        status="pass" if blocking_scripts == 0 else "warning",
                        message=f"{blocking_scripts} render-blocking script(s) in <head> on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "blocking_scripts": blocking_scripts},
                    ))

                    # Large images
                    large_imgs = [
                        u for u, size in resource_sizes.items()
                        if size > LARGE_IMAGE_THRESHOLD_BYTES and any(
                            ext in u.lower() for ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
                        )
                    ]
                    results.append(TestResult(
                        test_name=f"{SUITE}:large_images",
                        status="pass" if not large_imgs else "warning",
                        message=f"{len(large_imgs)} image(s) over 500KB on {url}" if large_imgs else f"No oversized images on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "large_images": large_imgs[:5]},
                    ))

                    # Compression check (via encoding header)
                    compression_info: dict = await page.evaluate(
                        """async () => {
                            try {
                                const resp = await fetch(window.location.href, {method: 'HEAD'});
                                return {encoding: resp.headers.get('content-encoding') || 'none'};
                            } catch (e) {
                                return {encoding: 'unknown'};
                            }
                        }"""
                    )
                    encoding = compression_info.get("encoding", "none")
                    compressed = encoding in ("gzip", "br", "deflate", "zstd")
                    results.append(TestResult(
                        test_name=f"{SUITE}:compression",
                        status="pass" if compressed else "warning",
                        message=f"Compression: {encoding} on {url}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": url, "content_encoding": encoding},
                    ))

                except Exception as exc:
                    logger.error("Asset check failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"Asset check error on {url}: {exc}",
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
