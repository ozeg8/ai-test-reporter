"""Playwright test execution engine — orchestrates all test suites."""

import argparse
import asyncio
import os
import sys
from typing import Optional

from src.crawler import crawl, CrawlResult
from src.report_generator import generate_report
from src.utils import TestResult, get_logger

logger = get_logger(__name__)

# Lazy imports per suite to avoid loading unused modules
SUITE_MAP: dict[str, str] = {
    "smoke": "test_suites.smoke",
    "functional": "test_suites.functional",
    "ui": "test_suites.ui_visual",
    "responsive": "test_suites.responsive",
    "a11y": "test_suites.accessibility",
    "performance": "test_suites.performance",
    "seo": "test_suites.seo",
    "security": "test_suites.security",
    "links": "test_suites.links",
    "console": "test_suites.console_errors",
    "forms": "test_suites.forms",
    "crossbrowser": "test_suites.cross_browser",
    "api": "test_suites.api_monitor",
    "cookies": "test_suites.cookies",
    "assets": "test_suites.assets",
    "i18n": "test_suites.i18n",
}


async def run_suite(
    suite_name: str,
    crawl_result: CrawlResult,
) -> list[TestResult]:
    """Dynamically import and execute a test suite.

    Args:
        suite_name: Key from SUITE_MAP.
        crawl_result: Pre-crawled site data.

    Returns:
        List of TestResult from the suite.
    """
    import importlib

    module_path = SUITE_MAP.get(suite_name)
    if not module_path:
        logger.warning("Unknown suite: %s", suite_name)
        return []

    try:
        module = importlib.import_module(module_path)
        run_fn = getattr(module, "run")
        results: list[TestResult] = await run_fn(crawl_result)
        return results
    except Exception as exc:
        logger.error("Suite %s crashed: %s", suite_name, exc)
        return [
            TestResult(
                test_name=f"{suite_name}:error",
                status="fail",
                message=f"Suite crashed: {exc}",
                screenshot_path=None,
                duration_ms=0.0,
                details=None,
            )
        ]


async def run_tests(
    url: str,
    test_type: str,
    output: Optional[str] = None,
) -> str:
    """Crawl the target URL then run the requested test suite(s).

    Args:
        url: Target website URL.
        test_type: Suite name or "all".
        output: Optional output filename (without .html extension).

    Returns:
        Path to the generated HTML report.
    """
    logger.info("Crawling %s ...", url)
    crawl_result = await crawl(url)

    if not crawl_result.pages:
        logger.error("No pages discovered for %s", url)
        sys.exit(1)

    suites_to_run: list[str]
    if test_type == "all":
        suites_to_run = list(SUITE_MAP.keys())
    else:
        suites_to_run = [test_type]

    all_results: list[TestResult] = []
    for suite in suites_to_run:
        logger.info("Running suite: %s", suite)
        results = await run_suite(suite, crawl_result)
        all_results.extend(results)
        passed = sum(1 for r in results if r.status == "pass")
        failed = sum(1 for r in results if r.status == "fail")
        logger.info("  %s: %d pass, %d fail", suite, passed, failed)

    report_path = generate_report(url, all_results, output)
    print(f"\nReport: {report_path}")
    return report_path


def main() -> None:
    """CLI entry point: python -m src.test_runner <url> --type <suite>."""
    parser = argparse.ArgumentParser(description="AI Test Reporter")
    parser.add_argument("url", help="Target website URL")
    parser.add_argument(
        "--type",
        default="smoke",
        choices=list(SUITE_MAP.keys()) + ["all"],
        help="Test suite to run (default: smoke)",
    )
    parser.add_argument("--output", help="Output filename (without .html)", default=None)
    parser.add_argument("--headed", action="store_true", help="Run with visible browser window")
    args = parser.parse_args()

    if args.headed:
        os.environ["AI_REPORTER_HEADED"] = "1"

    # Set a unique run ID so screenshots/reports land in an isolated subfolder
    from datetime import datetime
    from urllib.parse import urlparse
    hostname = urlparse(args.url).netloc.replace(".", "_").replace("www_", "")
    run_id = f"{hostname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.environ["AI_REPORTER_RUN_ID"] = run_id
    logger.info("Run ID: %s", run_id)

    asyncio.run(run_tests(args.url, args.type, args.output))


if __name__ == "__main__":
    main()
