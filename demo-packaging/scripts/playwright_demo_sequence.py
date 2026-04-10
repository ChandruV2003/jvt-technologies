#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_SITE_URL = (
    "file:///Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/site/index.html"
)
DEFAULT_DEMO_URL = "http://127.0.0.1:8000/demo"


def wait(ms: int, page) -> None:
    page.wait_for_timeout(ms)


def run_sequence(
    site_url: str,
    demo_url: str,
    output_dir: Path | None,
    headless: bool,
    width: int,
    height: int,
) -> None:
    output_dir = output_dir.resolve() if output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            args=[
                f"--window-size={width},{height}",
                "--window-position=90,80",
                "--disable-features=Translate,NotificationTriggers",
            ],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(output_dir) if output_dir else None,
            record_video_size={"width": width, "height": height} if output_dir else None,
        )
        page = context.new_page()
        page.goto(site_url, wait_until="load")
        wait(6500, page)

        page.goto(demo_url, wait_until="networkidle")
        page.bring_to_front()
        wait(3500, page)

        page.click("#reset-demo-btn")
        page.locator("#upload-status").wait_for()
        page.wait_for_function(
            "document.querySelector('#upload-status').textContent.includes('clean recording state')"
        )
        wait(1500, page)

        page.click("#load-sample-pack-btn")
        page.wait_for_function(
            "document.querySelector('#document-count').textContent.includes('3 indexed')",
            timeout=10000,
        )
        wait(3200, page)

        page.select_option("#provider-select", "mlx-local")
        wait(500, page)
        page.click('[data-question=\"What does the billing policy say about disputed invoices?\"]')
        wait(500, page)
        page.click('#question-form button[type="submit"]')
        page.wait_for_function(
            """
            () => {
              const status = document.querySelector('#question-status')?.textContent || '';
              const answer = document.querySelector('#answer-text')?.textContent || '';
              return status.includes('Answer generated.') && answer.trim().length > 40;
            }
            """,
            timeout=30000,
        )
        page.wait_for_function(
            "() => document.querySelectorAll('#citation-list .citation-card').length >= 1",
            timeout=10000,
        )
        wait(7000, page)

        citation_target = page.locator("#citation-list")
        citation_target.scroll_into_view_if_needed()
        wait(6000, page)

        page.goto(f"{site_url}#contact", wait_until="load")
        wait(8000, page)

        page.close()
        context.close()
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the JVT demo sequence in Playwright Chromium.")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    parser.add_argument("--demo-url", default=DEFAULT_DEMO_URL)
    parser.add_argument("--video-dir", type=Path)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    try:
        run_sequence(
            site_url=args.site_url,
            demo_url=args.demo_url,
            output_dir=args.video_dir,
            headless=args.headless,
            width=args.width,
            height=args.height,
        )
    except PlaywrightTimeoutError as exc:
        raise SystemExit(f"Playwright demo sequence timed out: {exc}") from exc


if __name__ == "__main__":
    main()
