# AI Test Reporter

Automated website testing tool powered by Claude Code. Give it a URL and test type — it crawls the site, generates tests, runs them with Playwright, and produces a professional HTML report. No API keys needed — Claude Code IS the AI.

## How It Works

User opens this project in Claude Code (VS Code or terminal) and says:
- "Smoke test https://example.com"
- "Run all tests on https://example.com"  
- "UI test https://example.com and generate report"

Claude Code reads this CLAUDE.md, understands the project structure, writes the appropriate Playwright tests, executes them, and generates an HTML report.

## Project Structure

```
ai-test-reporter/
├── src/
│   ├── crawler.py          # Discovers pages and elements on target site
│   ├── test_runner.py       # Playwright test execution engine
│   ├── report_generator.py  # HTML report builder with Jinja2
│   └── utils.py             # Helpers: logging, file ops, timing
├── test_suites/
│   ├── smoke.py             # Smoke test checks
│   ├── functional.py        # Form & flow tests
│   ├── ui_visual.py         # Layout & visual checks
│   ├── responsive.py        # Mobile/tablet/desktop screenshots
│   ├── accessibility.py     # WCAG 2.1 checks (axe-core)
│   ├── performance.py       # Core Web Vitals (LCP, FCP, CLS, TTFB)
│   ├── seo.py               # Meta tags, headings, sitemap, robots
│   ├── security.py          # Headers, mixed content, cookie flags
│   ├── links.py             # Broken link/image checker
│   ├── console_errors.py    # JS errors, unhandled rejections
│   ├── forms.py             # Form validation, XSS input, edge cases
│   ├── cross_browser.py     # Chromium, Firefox, WebKit comparison
│   ├── api_monitor.py       # Network requests, response codes, timing
│   ├── cookies.py           # GDPR, 3rd party, secure flags
│   ├── assets.py            # Unused CSS/JS, unoptimized images
│   └── i18n.py              # Hardcoded text, encoding, RTL detection
├── templates/
│   └── report.html          # Jinja2 HTML report template
├── reports/                  # Generated reports go here (gitignored)
├── screenshots/              # Test screenshots (gitignored)
├── tests/                    # Unit tests for the tool itself
│   ├── test_crawler.py
│   ├── test_runner.py
│   └── test_report.py
├── CLAUDE.md                 # This file
├── requirements.txt
├── setup.py
├── .gitignore
└── README.md
```

## Commands

- `pip install -e .` — install in development mode
- `pip install playwright && playwright install` — install browsers
- `python -m src.crawler https://example.com` — crawl only
- `python -m src.test_runner https://example.com --type smoke` — run specific test
- `python -m src.test_runner https://example.com --type all` — run all tests
- `pytest tests/ -v` — run unit tests for the tool itself

## Test Types and What They Check

When user asks to test a site, determine which test suite to run:

### Smoke Test (--type smoke)
- Every discovered page returns HTTP 200
- No console errors on any page
- All images load (no broken src)
- Page loads under 10 seconds
- Title and favicon exist

### Functional Test (--type functional)
- All forms are submittable (test with empty + valid data)
- Navigation links work and go to correct pages
- Search functionality returns results
- Login/register flows if detected
- Buttons trigger expected actions

### UI/Visual Test (--type ui)
- No elements overflow their containers
- No overlapping elements (z-index issues)
- Text is readable (minimum font size 12px)
- Images have proper aspect ratios
- No horizontal scrollbar on any page

### Responsive Test (--type responsive)
- Screenshot at 375px (mobile), 768px (tablet), 1440px (desktop)
- Navigation is accessible on all viewports
- No content cut off on smaller screens
- Touch targets minimum 44x44px on mobile

### Accessibility Test (--type a11y)
- Run axe-core via playwright-axe
- All images have alt text
- Color contrast ratio >= 4.5:1
- All interactive elements keyboard-accessible
- Proper heading hierarchy (h1 > h2 > h3)
- ARIA labels on custom widgets
- Focus indicators visible

### Performance Test (--type performance)
- Measure LCP (Largest Contentful Paint) — target < 2.5s
- Measure FCP (First Contentful Paint) — target < 1.8s
- Measure CLS (Cumulative Layout Shift) — target < 0.1
- Measure TTFB (Time To First Byte) — target < 800ms
- Total page weight in MB
- Number of HTTP requests

### SEO Test (--type seo)
- Title tag exists and under 60 chars
- Meta description exists and under 160 chars
- H1 tag exists and is unique per page
- Canonical URL present
- robots.txt accessible
- Sitemap.xml exists
- Open Graph tags present
- No duplicate meta tags

### Security Test (--type security)
- HTTPS enforced (HTTP redirects to HTTPS)
- Security headers present: CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- No mixed content (HTTP resources on HTTPS page)
- Cookies have Secure and HttpOnly flags
- No sensitive data in URL parameters

### Link Validation (--type links)
- All internal links return 200
- External links checked (timeout 10s)
- No redirect chains longer than 3
- Anchor links point to existing IDs
- No mailto: links with typos

### Console/JS Error Scan (--type console)
- Capture all console.error messages
- Detect unhandled promise rejections
- Flag deprecation warnings
- Count total warnings vs errors

### Form Validation Test (--type forms)
- Submit empty forms — proper error messages shown?
- Enter XSS payloads (<script>alert(1)</script>) — escaped?
- Test email fields with invalid formats
- Test max length boundaries
- Test special characters (emoji, unicode)

### Cross-Browser Test (--type crossbrowser)
- Run smoke tests on Chromium, Firefox, WebKit
- Compare screenshots across browsers
- Flag visual differences > 5% pixel diff

### API Monitor (--type api)
- Intercept all XHR/fetch requests during page load
- Log response status codes and times
- Flag any 4xx or 5xx responses
- Measure average API response time

### Cookie/Storage Audit (--type cookies)
- List all cookies with their attributes
- Flag 3rd party cookies
- Check for cookie consent mechanism
- Measure localStorage/sessionStorage usage
- Verify Secure and SameSite attributes

### Asset Check (--type assets)
- Detect render-blocking resources
- Flag images over 500KB without optimization
- Check for unused CSS rules
- Verify gzip/brotli compression

### i18n Test (--type i18n)
- Detect hardcoded strings in HTML
- Check charset is UTF-8
- Detect RTL content handling
- Verify date/currency format patterns

## Conventions

- Python 3.11+ with type hints on all functions
- Google-style docstrings
- async/await for all Playwright operations
- Every test suite returns a standardized TestResult dataclass:
  ```python
  @dataclass
  class TestResult:
      test_name: str
      status: str  # "pass", "fail", "warning", "skip"
      message: str
      screenshot_path: Optional[str]
      duration_ms: float
      details: Optional[dict]
  ```
- All times measured in milliseconds
- Screenshots saved as PNG in screenshots/ directory
- Explicit timeouts on all Playwright operations (max 30s)
- Never crash on a single test failure — catch, log, continue

## Report Format

The HTML report must:
- Be a single standalone file (inline CSS, base64 images)
- Show summary at top: total tests, pass, fail, warning counts
- Group results by test type with collapsible sections
- Include screenshots inline (base64 encoded)
- Show timing for each test
- Have a professional, clean design
- Work offline (no external dependencies)
- Include timestamp and target URL

## Rules

- NEVER hardcode URLs or test data — always parameterize
- NEVER skip error handling — every Playwright call needs try/except
- ALWAYS use headless browser mode by default
- ALWAYS clean up browser instances after tests
- ALWAYS create the reports/ and screenshots/ directories if they don't exist
- Test results must be deterministic — same site, same results (within timing variance)
- If a test suite is not applicable (e.g., no forms found for form test), return "skip" status, not "fail"
