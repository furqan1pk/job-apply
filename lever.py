"""Lever ATS adapter — direct Playwright selectors."""

import asyncio
import random
import re
from pathlib import Path
from playwright.async_api import Page

from config import SCREENSHOT_DIR
from questions import match_rule, answer_with_llm


CAPTCHA_SELECTORS = [
    'iframe[src*="captcha"]', '.g-recaptcha', '.h-captcha',
    '.cf-turnstile', '[data-sitekey]',
]


async def apply(page: Page, url: str, profile: dict, resume_pdf: str, dry_run: bool = False) -> dict:
    """Fill and submit a Lever application.

    Lever URLs: job page is /jobs/UUID, apply page is /jobs/UUID/apply
    """
    result = {"status": "failed", "error": "", "title": "", "company": ""}

    # Ensure we're on the apply page
    apply_url = url.rstrip("/")
    if not apply_url.endswith("/apply"):
        apply_url += "/apply"

    print(f"  [LV] Navigating to {apply_url}")
    await page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(1, 2))

    # Extract title
    try:
        title_el = await page.query_selector("h2, .posting-headline h2, [class*='title']")
        if title_el:
            result["title"] = (await title_el.inner_text()).strip()
    except Exception:
        pass

    result["company"] = _extract_company(url)

    # Check CAPTCHA
    for sel in CAPTCHA_SELECTORS:
        if await page.query_selector(sel):
            result["status"] = "captcha"
            result["error"] = f"CAPTCHA detected: {sel}"
            return result

    # --- FILL STANDARD FIELDS ---
    print("  [LV] Filling standard fields...")
    await _safe_fill(page, 'input[name="name"]', profile['full_name'])
    await _safe_fill(page, 'input[name="email"]', profile['email'])
    await _safe_fill(page, 'input[name="phone"]', profile['phone'])
    await _safe_fill(page, 'input[name="org"]', profile['current_company'])

    # URLs
    await _safe_fill(page, 'input[name="urls[LinkedIn]"]', profile['linkedin'])
    await _safe_fill(page, 'input[name="urls[GitHub]"]', profile['github'])
    await _safe_fill(page, 'input[name="urls[Portfolio]"]', profile['portfolio'])
    await _safe_fill(page, 'input[name="urls[Other]"]', profile['website'])

    # Location
    await _safe_fill(page, 'input[name="location"]', f"{profile['city']}, {profile['state']}")

    await asyncio.sleep(random.uniform(0.5, 1))

    # --- UPLOAD RESUME ---
    print("  [LV] Uploading resume...")
    resume_input = await page.query_selector('input[name="resume"][type="file"], input[type="file"]')
    if resume_input and Path(resume_pdf).exists():
        await resume_input.set_input_files(resume_pdf)
        await asyncio.sleep(2)
        print("  [LV] Resume uploaded [OK]")
    else:
        print("  [LV] [WARN] Resume input not found or PDF missing")

    # --- CUSTOM QUESTIONS ---
    print("  [LV] Scanning custom questions...")
    custom_questions = await _scan_lever_questions(page)
    print(f"  [LV] Found {len(custom_questions)} custom questions")

    unanswered = []
    for q in custom_questions:
        answer = match_rule(q["text"], profile)
        if answer is not None:
            q["answer"] = answer
        else:
            unanswered.append(q)

    if unanswered:
        print(f"  [LV] Asking Gemini for {len(unanswered)} custom questions...")
        llm_answers = answer_with_llm(unanswered, result["title"], result["company"])
        for q in unanswered:
            q["answer"] = llm_answers.get(q["id"], "")

    for q in custom_questions:
        if q.get("answer"):
            await _fill_lever_question(page, q)
            await asyncio.sleep(random.uniform(0.3, 0.7))

    # --- SCREENSHOT ---
    screenshot_name = f"lever_{result['title'][:30].replace(' ', '_')}.png"
    screenshot_path = SCREENSHOT_DIR / screenshot_name
    await page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"  [LV] Screenshot saved: {screenshot_path}")

    # --- SUBMIT ---
    if dry_run:
        result["status"] = "dry_run"
        print("  [LV] DRY RUN — not submitting")
        return result

    submit_btn = await page.query_selector('button[type="submit"], .postings-btn-submit, button:has-text("Submit")')
    if submit_btn:
        print("  [LV] Submitting application...")
        await submit_btn.click()
        await asyncio.sleep(3)

        page_text = await page.inner_text("body")
        if any(kw in page_text.lower() for kw in ["thank you", "submitted", "received", "application"]):
            result["status"] = "applied"
            print("  [LV] [OK] Application submitted!")
            await page.screenshot(path=str(SCREENSHOT_DIR / f"confirm_{screenshot_name}"))
        else:
            result["status"] = "applied"  # Assume success
            print("  [LV] [OK] Submitted (no confirmation detected)")
    else:
        result["error"] = "Submit button not found"
        print("  [LV] [FAIL] Submit button not found")

    return result


async def _safe_fill(page: Page, selector: str, value: str) -> bool:
    """Fill a field if it exists."""
    try:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            await el.fill(value)
            return True
    except Exception:
        pass
    return False


async def _scan_lever_questions(page: Page) -> list[dict]:
    """Scan Lever form for custom questions."""
    questions = []
    cards = await page.query_selector_all('.custom-question, [class*="application-question"]')

    for card in cards:
        try:
            label = await card.query_selector("label, .custom-question-title")
            if not label:
                continue
            label_text = (await label.inner_text()).strip()

            input_el = await card.query_selector("input, textarea, select")
            if not input_el:
                continue

            input_id = await input_el.get_attribute("name") or await input_el.get_attribute("id") or ""
            tag = await input_el.evaluate("el => el.tagName.toLowerCase()")
            input_type = await input_el.get_attribute("type") or "text"

            q_type = "text"
            if tag == "textarea":
                q_type = "textarea"
            elif tag == "select":
                q_type = "select"
            elif input_type == "radio":
                q_type = "radio"
            elif input_type == "checkbox":
                q_type = "checkbox"

            questions.append({
                "id": input_id,
                "text": label_text,
                "type": q_type,
                "selector": f"[name='{input_id}']" if input_id else "",
            })
        except Exception:
            continue

    return questions


async def _fill_lever_question(page: Page, question: dict):
    """Fill a Lever custom question."""
    sel = question.get("selector", "")
    answer = question.get("answer", "")
    q_type = question.get("type", "text")

    if not sel or not answer:
        return

    try:
        if q_type in ("text", "textarea"):
            await _safe_fill(page, sel, answer)
        elif q_type == "select":
            el = await page.query_selector(sel)
            if el:
                await el.select_option(label=answer)
        elif q_type == "radio":
            radios = await page.query_selector_all(f"{sel}")
            for radio in radios:
                val = await radio.get_attribute("value") or ""
                if answer.lower() in val.lower():
                    await radio.click()
                    break
    except Exception as e:
        print(f"  [LV] [WARN] Could not fill '{question['text'][:40]}': {e}")


def _extract_company(url: str) -> str:
    """Extract company from Lever URL."""
    match = re.search(r"lever\.co/([^/]+)", url)
    return match.group(1) if match else "company"
