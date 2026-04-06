"""HTML report builder with Jinja2 — produces a single standalone file."""

import base64
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.utils import TestResult, get_logger, reports_dir

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# ── Gherkin mapping ──────────────────────────────────────────────────────────

_GIVEN_MAP: dict[str, str] = {
    "smoke":       "the website is accessible and a Chromium browser session is open",
    "functional":  "the website's interactive elements and navigation are loaded",
    "ui":          "the page is rendered at 1440px desktop viewport",
    "responsive":  "the page is loaded across mobile, tablet, and desktop viewports",
    "a11y":        "the page is loaded with accessibility evaluation tools active",
    "performance": "the page is loaded with Performance Observer and Navigation Timing active",
    "seo":         "the page metadata and search-engine indexability are being evaluated",
    "security":    "the HTTP response headers and HTTPS configuration are under examination",
    "links":       "all hyperlinks on the page have been collected for validation",
    "console":     "the browser console is monitored for errors and warnings",
    "forms":       "interactive form elements are present on the page",
    "crossbrowser":"the page is loaded across Chromium, Firefox, and WebKit engines",
    "api":         "network request interception is active on the browser context",
    "cookies":     "the browser cookie jar and web storage APIs are accessible",
    "assets":      "page resource loading is being profiled via Resource Timing API",
    "i18n":        "the page HTML and visible text content are being analyzed",
}

_WHEN_MAP: dict[str, str] = {
    "http_status":                    "I request the page URL and read the HTTP response code",
    "load_time":                      "I measure total time from navigation start to the load event",
    "title":                          "I inspect the document <title> element",
    "favicon":                        "I look for a <link rel='icon'> element in <head>",
    "console_errors":                 "I collect all console.error() calls during page load",
    "images":                         "I check naturalWidth of every <img> element",
    "navigation":                     "I follow each navigation link and record the HTTP status",
    "form_submit":                    "I click the form submit button and observe the UI response",
    "horizontal_scroll":              "I compare document.documentElement.scrollWidth to clientWidth",
    "overflow":                       "I measure getBoundingClientRect() of every element against viewport",
    "font_size":                      "I compute computed font-size of all visible text elements",
    "screenshot":                     "I capture a full-page screenshot",
    "mobile":                         "I set the viewport to 375×812px and navigate to the page",
    "tablet":                         "I set the viewport to 768×1024px and navigate to the page",
    "desktop":                        "I set the viewport to 1440×900px and navigate to the page",
    "img_alt":                        "I check every <img> element for a non-empty alt attribute",
    "heading_hierarchy":              "I traverse heading elements checking for level-skip violations",
    "h1_count":                       "I count the number of <h1> tags on the page",
    "unlabeled_controls":             "I check buttons and links for accessible name (text/aria-label)",
    "lang_attr":                      "I inspect the lang attribute on the <html> element",
    "fcp":                            "I read the first-contentful-paint entry from PerformanceObserver",
    "ttfb":                           "I calculate responseStart minus requestStart from Navigation Timing",
    "page_weight":                    "I sum transferSize from all Resource Timing entries",
    "meta_description":               "I read the content of meta[name=description]",
    "h1":                             "I count and inspect <h1> tags across the page",
    "open_graph":                     "I check for og:title and og:description meta tags",
    "canonical":                      "I look for a <link rel=canonical> element",
    "robots_txt":                     "I send an HTTP GET to /robots.txt",
    "sitemap":                        "I send an HTTP GET to /sitemap.xml",
    "https":                          "I verify the site URL uses the HTTPS scheme",
    "https_redirect":                 "I send an HTTP request and check for a redirect to HTTPS",
    "sensitive_url_params":           "I scan all discovered URLs for sensitive query parameter names",
    "header_content_security_policy": "I check the response for a Content-Security-Policy header",
    "header_strict_transport_security":"I check the response for a Strict-Transport-Security header",
    "header_x_frame_options":         "I check the response for an X-Frame-Options header",
    "header_x_content_type_options":  "I check the response for an X-Content-Type-Options header",
    "cookie_flags":                   "I inspect Set-Cookie headers for Secure and HttpOnly attributes",
    "internal":                       "I request each internal link and follow redirects up to 5 hops",
    "external":                       "I request each external link with a 10-second timeout",
    "errors":                         "I collect all console.error() messages during page load",
    "warnings":                       "I collect all console.warn() messages during page load",
    "rejections":                     "I listen for unhandled Promise rejection events",
    "xss_reflection":                 "I submit a <script>alert()</script> payload into text inputs",
    "special_chars":                  "I submit emoji and unicode characters into form text inputs",
    "chromium":                       "I load the page in a Chromium browser and capture the result",
    "firefox":                        "I load the page in a Firefox browser and capture the result",
    "webkit":                         "I load the page in a WebKit browser and capture the result",
    "requests":                       "I intercept all XHR/fetch calls and log status codes and timing",
    "total":                          "I count all cookies present after page load",
    "third_party":                    "I identify cookies whose domain differs from the site domain",
    "secure_flag":                    "I check each cookie object for the Secure attribute",
    "httponly_flag":                   "I check each cookie object for the HttpOnly attribute",
    "samesite":                       "I check each cookie object for a SameSite attribute",
    "storage":                        "I measure character counts in localStorage and sessionStorage",
    "consent_banner":                 "I search visible DOM elements for cookie consent keywords",
    "render_blocking":                "I count synchronous <script> tags inside <head>",
    "large_images":                   "I compare image resource transfer sizes to the 500KB threshold",
    "compression":                    "I check the Content-Encoding header on the page response",
    "charset":                        "I inspect the meta charset tag and document.characterSet",
    "lang":                           "I read the lang attribute from the <html> element",
    "rtl":                            "I check the dir attribute and count [dir=rtl] elements",
    "hardcoded_formats":              "I scan visible body text for date and currency patterns",
    "page_error":                     "I navigate to the page and observe the browser response",
    "error":                          "the test suite executes its primary check",
    "no_forms":                       "I search the page DOM for <form> elements",
    "no_links":                       "I search the page DOM for <a href> elements",
    "no_testable_forms":              "I attempt to interact with discovered form elements",
    "no_tests":                       "I evaluate available test targets on the page",
}

_STATUS_THEN: dict[str, str] = {
    "pass":    "passes",
    "fail":    "fails",
    "warning": "issues a warning",
    "skip":    "is skipped",
}


def _to_gherkin(result: TestResult) -> dict[str, str]:
    """Convert a TestResult into Cucumber/Gherkin Given/When/Then steps.

    Args:
        result: A TestResult dataclass instance.

    Returns:
        Dict with keys 'given', 'when', 'then'.
    """
    parts = result.test_name.split(":", 1)
    suite = parts[0]
    check = parts[1] if len(parts) > 1 else "check"

    given = _GIVEN_MAP.get(suite, f"the {suite} test suite is initialised")
    when  = _WHEN_MAP.get(check, f"I run the '{check}' check")
    verb  = _STATUS_THEN.get(result.status, result.status)
    then  = f"the assertion {verb}: {result.message}"

    return {
        "given": f"Given {given}",
        "when":  f"When {when}",
        "then":  f"Then {then}",
    }


# ── SVG pie chart ────────────────────────────────────────────────────────────

_CHART_COLORS: dict[str, str] = {
    "pass":    "#10b981",
    "fail":    "#ef4444",
    "warning": "#f59e0b",
    "skip":    "#6366f1",
}


def _pie_svg(counts: dict) -> str:
    """Generate an inline SVG donut-chart for pass/fail/warn/skip counts.

    Args:
        counts: Dict with keys total, pass, fail, warning, skip.

    Returns:
        SVG markup string.
    """
    total = counts["total"]
    if total == 0:
        return "<svg viewBox='0 0 200 200'><text x='100' y='105' text-anchor='middle' fill='#94a3b8' font-size='14'>No data</text></svg>"

    cx, cy, r_outer, r_inner = 100, 100, 85, 52
    segments = [
        ("pass",    counts["pass"],    _CHART_COLORS["pass"]),
        ("fail",    counts["fail"],    _CHART_COLORS["fail"]),
        ("warning", counts["warning"], _CHART_COLORS["warning"]),
        ("skip",    counts["skip"],    _CHART_COLORS["skip"]),
    ]

    parts: list[str] = ['<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">']
    angle = -90.0  # start from top

    for _name, count, color in segments:
        if count == 0:
            continue
        sweep = (count / total) * 360.0
        end = angle + sweep
        a1, a2 = math.radians(angle), math.radians(end)

        x1o = cx + r_outer * math.cos(a1)
        y1o = cy + r_outer * math.sin(a1)
        x2o = cx + r_outer * math.cos(a2)
        y2o = cy + r_outer * math.sin(a2)
        x1i = cx + r_inner * math.cos(a2)
        y1i = cy + r_inner * math.sin(a2)
        x2i = cx + r_inner * math.cos(a1)
        y2i = cy + r_inner * math.sin(a1)

        large = 1 if sweep > 180 else 0
        d = (
            f"M {x1o:.3f} {y1o:.3f} "
            f"A {r_outer} {r_outer} 0 {large} 1 {x2o:.3f} {y2o:.3f} "
            f"L {x1i:.3f} {y1i:.3f} "
            f"A {r_inner} {r_inner} 0 {large} 0 {x2i:.3f} {y2i:.3f} Z"
        )
        parts.append(f'<path d="{d}" fill="{color}"/>')
        angle = end

    # Center label
    pass_pct = round(counts["pass"] / total * 100) if total else 0
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="#0f172a"/>')
    parts.append(f'<text x="{cx}" y="{cy - 8}" text-anchor="middle" fill="#f1f5f9" font-size="26" font-weight="800">{pass_pct}%</text>')
    parts.append(f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" fill="#94a3b8" font-size="11">pass rate</text>')
    parts.append('</svg>')

    return "\n".join(parts)


# ── Timeline data ─────────────────────────────────────────────────────────────

def _timeline(results: list[TestResult]) -> list[dict]:
    """Build per-suite timeline entries from ordered result list.

    Args:
        results: All TestResult instances in execution order.

    Returns:
        List of dicts: {suite, duration_ms, start_ms, status, pct_start, pct_width}
    """
    # Aggregate by suite
    suite_data: dict[str, dict] = {}
    for r in results:
        suite = r.test_name.split(":")[0]
        if suite not in suite_data:
            suite_data[suite] = {"duration_ms": 0.0, "has_fail": False, "has_warn": False}
        suite_data[suite]["duration_ms"] += r.duration_ms
        if r.status == "fail":
            suite_data[suite]["has_fail"] = True
        if r.status == "warning":
            suite_data[suite]["has_warn"] = True

    total_ms = sum(v["duration_ms"] for v in suite_data.values()) or 1

    timeline: list[dict] = []
    start = 0.0
    for suite, data in suite_data.items():
        dur = data["duration_ms"]
        color = (_CHART_COLORS["fail"] if data["has_fail"]
                 else _CHART_COLORS["warning"] if data["has_warn"]
                 else _CHART_COLORS["pass"])
        timeline.append({
            "suite":       suite,
            "duration_ms": round(dur),
            "start_ms":    round(start),
            "color":       color,
            "pct_start":   round(start / total_ms * 100, 2),
            "pct_width":   max(round(dur / total_ms * 100, 2), 0.5),
        })
        start += dur

    return timeline


# ── Screenshot encoding ───────────────────────────────────────────────────────

def _encode_screenshot(path: Optional[str]) -> Optional[str]:
    """Base64-encode a PNG screenshot for inline embedding.

    Args:
        path: Filesystem path to the PNG file.

    Returns:
        Base64 data URI string or None.
    """
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        data = fh.read()
    return "data:image/png;base64," + base64.b64encode(data).decode()


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_report(
    target_url: str,
    results: list[TestResult],
    output_filename: Optional[str] = None,
) -> str:
    """Build an HTML report and write it to the reports/ directory.

    Args:
        target_url: The URL that was tested.
        results: List of TestResult objects from all suites.
        output_filename: Optional custom filename (without extension).

    Returns:
        Absolute path to the generated report file.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html")

    # Counts
    counts = {
        "total":   len(results),
        "pass":    sum(1 for r in results if r.status == "pass"),
        "fail":    sum(1 for r in results if r.status == "fail"),
        "warning": sum(1 for r in results if r.status == "warning"),
        "skip":    sum(1 for r in results if r.status == "skip"),
    }

    # Enrich each result
    enriched: list[dict] = []
    for r in results:
        enriched.append({
            "test_name":   r.test_name,
            "status":      r.status,
            "message":     r.message,
            "duration_ms": round(r.duration_ms, 1),
            "details":     json.dumps(r.details, indent=2) if r.details else None,
            "screenshot":  _encode_screenshot(r.screenshot_path),
            "gherkin":     _to_gherkin(r),
        })

    # Suite groups (preserve insertion order)
    suites_seen: list[str] = []
    suite_map: dict[str, list[dict]] = {}
    for e in enriched:
        s = e["test_name"].split(":")[0]
        if s not in suite_map:
            suite_map[s] = []
            suites_seen.append(s)
        suite_map[s].append(e)

    suite_groups: list[dict] = []
    for s in suites_seen:
        items = suite_map[s]
        suite_groups.append({
            "name":       s,
            "results":    items,
            "pass_count":  sum(1 for i in items if i["status"] == "pass"),
            "fail_count":  sum(1 for i in items if i["status"] == "fail"),
            "warn_count":  sum(1 for i in items if i["status"] == "warning"),
            "skip_count":  sum(1 for i in items if i["status"] == "skip"),
        })

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pie_svg   = _pie_svg(counts)
    timeline  = _timeline(results)
    total_duration_s = round(sum(r.duration_ms for r in results) / 1000, 1)

    html = template.render(
        target_url=target_url,
        timestamp=timestamp,
        counts=counts,
        suite_groups=suite_groups,
        pie_svg=pie_svg,
        timeline=timeline,
        total_duration_s=total_duration_s,
    )

    rdir = reports_dir()
    if output_filename:
        fname = f"{output_filename}.html"
    else:
        safe = target_url.replace("://", "_").replace("/", "_").replace(".", "_")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"report_{safe}_{ts}.html"

    out_path = os.path.join(rdir, fname)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    logger.info("Report written: %s", out_path)
    return out_path
