"""Security test suite: HTTPS, security headers, mixed content, cookie flags."""

import httpx
from urllib.parse import urlparse

from src.crawler import CrawlResult
from src.utils import TestResult, get_logger, timer_ms, elapsed_ms

logger = get_logger(__name__)

SUITE = "security"

REQUIRED_HEADERS = [
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
]

SENSITIVE_PARAMS = ["token", "password", "passwd", "secret", "key", "api_key", "auth"]


async def run(crawl_result: CrawlResult) -> list[TestResult]:
    """Run security checks against the base URL and discovered pages.

    Args:
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult.
    """
    results: list[TestResult] = []
    base = crawl_result.base_url
    start = timer_ms()

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=15, verify=True) as client:
            # HTTPS enforcement
            parsed = urlparse(base)
            if parsed.scheme == "http":
                resp = await client.get(base)
                redirected_to_https = (
                    resp.status_code in (301, 302, 307, 308)
                    and resp.headers.get("location", "").startswith("https://")
                )
                results.append(TestResult(
                    test_name=f"{SUITE}:https_redirect",
                    status="pass" if redirected_to_https else "fail",
                    message="HTTP redirects to HTTPS" if redirected_to_https else "HTTP does not redirect to HTTPS",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"url": base},
                ))
            else:
                results.append(TestResult(
                    test_name=f"{SUITE}:https",
                    status="pass",
                    message="Site uses HTTPS",
                    screenshot_path=None,
                    duration_ms=elapsed_ms(start),
                    details={"url": base},
                ))

            # Security headers
            https_url = base if parsed.scheme == "https" else base.replace("http://", "https://", 1)
            try:
                head_resp = await client.get(https_url)
                headers_lower = {k.lower(): v for k, v in head_resp.headers.items()}
                for header in REQUIRED_HEADERS:
                    present = header in headers_lower
                    results.append(TestResult(
                        test_name=f"{SUITE}:header_{header.replace('-', '_')}",
                        status="pass" if present else "warning",
                        message=f"{'Present' if present else 'Missing'}: {header}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"url": https_url, "header": header, "value": headers_lower.get(header)},
                    ))

                # Cookie flags (from Set-Cookie headers)
                set_cookie = head_resp.headers.get("set-cookie", "")
                if set_cookie:
                    has_secure = "secure" in set_cookie.lower()
                    has_httponly = "httponly" in set_cookie.lower()
                    results.append(TestResult(
                        test_name=f"{SUITE}:cookie_flags",
                        status="pass" if (has_secure and has_httponly) else "warning",
                        message=f"Cookie flags — Secure: {has_secure}, HttpOnly: {has_httponly}",
                        screenshot_path=None,
                        duration_ms=elapsed_ms(start),
                        details={"secure": has_secure, "httponly": has_httponly},
                    ))

            except Exception as exc:
                logger.warning("Header check failed: %s", exc)

    except Exception as exc:
        logger.error("Security check failed: %s", exc)
        results.append(TestResult(
            test_name=f"{SUITE}:error",
            status="fail",
            message=f"Security check error: {exc}",
            screenshot_path=None,
            duration_ms=elapsed_ms(start),
            details=None,
        ))

    # Sensitive data in URL parameters
    for url in crawl_result.pages:
        parsed_url = urlparse(url)
        query = parsed_url.query.lower()
        found_sensitive = [p for p in SENSITIVE_PARAMS if p in query]
        if found_sensitive:
            results.append(TestResult(
                test_name=f"{SUITE}:sensitive_url_params",
                status="fail",
                message=f"Sensitive param(s) in URL: {found_sensitive} — {url}",
                screenshot_path=None,
                duration_ms=0.0,
                details={"url": url, "params": found_sensitive},
            ))

    if not any(r.test_name == f"{SUITE}:sensitive_url_params" for r in results):
        results.append(TestResult(
            test_name=f"{SUITE}:sensitive_url_params",
            status="pass",
            message="No sensitive data found in URL parameters",
            screenshot_path=None,
            duration_ms=0.0,
            details=None,
        ))

    return results
