"""Fast batch job application CLI — direct Playwright, ~30-60 sec per app."""

import argparse
import asyncio
import random
import time
from pathlib import Path

from playwright.async_api import async_playwright

from config import load_profile, detect_platform, RESUME_PDF, SCREENSHOT_DIR
from results import log_result
from report import generate_html_report
import greenhouse
import lever
import workday


async def apply_single(url: str, profile: dict, resume_pdf: str, dry_run: bool, headed: bool) -> dict:
    """Apply to a single job URL."""
    platform = detect_platform(url)

    if platform not in ("greenhouse", "lever", "workday"):
        print(f"  [SKIP]  Skipping unsupported platform: {platform} ({url})")
        return {"status": "skipped", "error": f"Unsupported platform: {platform}", "title": "", "company": "", "screenshots": []}

    async with async_playwright() as p:
        # Use persistent context with real Chrome user data to bypass Cloudflare
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        user_data = str(Path.home() / ".job-apply-chrome")  # Isolated profile

        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            executable_path=chrome_path,
            headless=not headed,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
            viewport={"width": 1366, "height": 900},
        )
        # Stealth: hide webdriver flag
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        browser = None  # persistent_context doesn't have separate browser
        page = await context.new_page()

        try:
            if platform == "greenhouse":
                result = await greenhouse.apply(page, url, profile, resume_pdf, dry_run)
            elif platform == "lever":
                result = await lever.apply(page, url, profile, resume_pdf, dry_run)
            elif platform == "workday":
                result = await workday.apply(page, url, profile, resume_pdf, dry_run)
            else:
                result = {"status": "skipped", "error": "unsupported", "title": "", "company": "", "screenshots": []}
        except Exception as e:
            result = {"status": "failed", "error": str(e)[:200], "title": "", "company": ""}
            print(f"  [FAIL] Error: {e}")
            # Save error screenshot
            try:
                await page.screenshot(path=str(SCREENSHOT_DIR / f"error_{platform}.png"))
            except Exception:
                pass
        finally:
            await context.close()
            if browser:
                await browser.close()

    return result


async def batch_apply(urls: list[str], profile: dict, resume_pdf: str, dry_run: bool, headed: bool):
    """Process multiple job URLs sequentially."""
    total = len(urls)
    applied = 0
    failed = 0
    skipped = 0

    print(f"\n{'='*60}")
    print(f"  Job Apply Engine — Batch Mode")
    print(f"  URLs: {total} | Dry run: {dry_run} | Headed: {headed}")
    print(f"  Resume: {resume_pdf}")
    print(f"{'='*60}\n")

    for i, url in enumerate(urls, 1):
        url = url.strip()
        if not url or url.startswith("#"):
            continue

        platform = detect_platform(url)
        print(f"\n[{i}/{total}] {platform.upper()} — {url}")
        print("-" * 60)

        start = time.time()
        result = await apply_single(url, profile, resume_pdf, dry_run, headed)
        duration = time.time() - start

        log_result(
            url=url,
            platform=platform,
            status=result["status"],
            duration_sec=duration,
            error=result.get("error", ""),
            job_title=result.get("title", ""),
            company=result.get("company", ""),
        )

        if result["status"] == "applied":
            applied += 1
        elif result["status"] in ("failed", "captcha"):
            failed += 1
        else:
            skipped += 1

        # Anti-bot delay between jobs
        if i < total:
            delay = random.uniform(3, 7)
            print(f"  [WAIT] Waiting {delay:.0f}s before next job...")
            await asyncio.sleep(delay)

    # Summary
    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETE")
    print(f"  [OK] Applied: {applied}")
    print(f"  [FAIL] Failed:  {failed}")
    print(f"  [SKIP]  Skipped: {skipped}")
    print(f"  [DIR] Results: results/")
    print(f"  [IMG] Screenshots: screenshots/")
    print(f"{'='*60}\n")

    # Generate HTML report with screenshots
    report_path = generate_html_report()
    if report_path:
        import os
        os.startfile(report_path)  # Auto-open in browser on Windows


def main():
    parser = argparse.ArgumentParser(description="Fast batch job application tool")
    parser.add_argument("--url", type=str, help="Single job URL to apply to")
    parser.add_argument("--urls", type=str, help="File with job URLs (one per line)")
    parser.add_argument("--dry-run", action="store_true", help="Fill forms but don't submit")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--resume", type=str, default=RESUME_PDF, help="Path to resume PDF")
    args = parser.parse_args()

    # Load profile
    profile = load_profile()
    print(f"Profile loaded: {profile['full_name']} ({profile['email']})")

    # Collect URLs
    urls = []
    if args.url:
        urls = [args.url]
    elif args.urls:
        with open(args.urls) as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        parser.print_help()
        return

    if not urls:
        print("No URLs provided.")
        return

    resume_pdf = args.resume
    if not Path(resume_pdf).exists():
        print(f"[FAIL] Resume not found: {resume_pdf}")
        return

    asyncio.run(batch_apply(urls, profile, resume_pdf, args.dry_run, args.headed))


if __name__ == "__main__":
    main()
