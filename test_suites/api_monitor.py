"""API monitor suite: intercept XHR/fetch, log status codes and timing."""

from playwright.async_api import async_playwright, Request, Response

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms

logger = get_logger(__name__)

SUITE = "api"


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Intercept all network requests during page load and flag errors.

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
                context = await browser.new_context()
                page = await context.new_page()
                start = timer_ms()

                api_calls: list[dict] = []
                request_times: dict[str, float] = {}

                def on_request(req: Request) -> None:
                    if req.resource_type in ("xhr", "fetch"):
                        request_times[req.url] = timer_ms()

                async def on_response(resp: Response) -> None:
                    req = resp.request
                    if req.resource_type in ("xhr", "fetch"):
                        req_start = request_times.pop(req.url, timer_ms())
                        api_calls.append({
                            "url": resp.url,
                            "status": resp.status,
                            "duration_ms": round(elapsed_ms(req_start), 1),
                        })

                page.on("request", on_request)
                page.on("response", lambda r: page.evaluate("() => undefined") or None)

                try:
                    await page.goto(url, timeout=30_000, wait_until="networkidle")

                    error_calls = [c for c in api_calls if c["status"] >= 400]
                    avg_time = (
                        sum(c["duration_ms"] for c in api_calls) / len(api_calls)
                        if api_calls else 0
                    )

                    results.append(TestResult(
                        test_name=f"{SUITE}:requests",
                        status="pass" if not error_calls else "fail",
                        message=f"{len(api_calls)} API call(s) on {url}, {len(error_calls)} error(s), avg {avg_time:.0f}ms",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={
                            "url": url,
                            "total_calls": len(api_calls),
                            "error_calls": error_calls[:10],
                            "avg_response_ms": round(avg_time, 1),
                        },
                    ))

                except Exception as exc:
                    logger.error("API monitor failed for %s: %s", url, exc)
                    results.append(TestResult(
                        test_name=f"{SUITE}:error",
                        status="fail",
                        message=f"API monitor error on {url}: {exc}",
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
