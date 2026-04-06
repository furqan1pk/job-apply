"""Greenhouse ATS adapter — direct Playwright selectors, ~30-60 sec per app."""

import asyncio
import random
import re
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from config import SCREENSHOT_DIR
from questions import match_rule, answer_with_llm


CAPTCHA_SELECTORS = [
    'iframe[src*="captcha"]', '.g-recaptcha', '.h-captcha',
    '.cf-turnstile', '[data-sitekey]', '#FunCaptcha',
]


async def apply(page: Page, url: str, profile: dict, resume_pdf: str, dry_run: bool = False) -> dict:
    """Fill and submit a Greenhouse application.

    Returns:
        {"status": "applied"|"failed"|"captcha", "error": str, "title": str, "company": str, "screenshots": list}
    """
    result = {"status": "failed", "error": "", "title": "", "company": "", "screenshots": []}
    step = 0

    def _safe_name(text, max_len=20):
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in text[:max_len])

    async def screenshot(label: str):
        nonlocal step
        step += 1
        safe_title = _safe_name(result.get('title', 'job'))
        name = f"gh_{safe_title}_{step:02d}_{label}.png"
        path = SCREENSHOT_DIR / name
        # Wait for React to finish rendering before capturing
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(path), full_page=True)
        result["screenshots"].append(str(path))
        print(f"  [GH] Screenshot {step}: {label}")

    # Navigate to job page
    print(f"  [GH] Navigating to {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(random.uniform(1, 2))

    # Extract job title and company from page
    try:
        title_el = await page.query_selector("h1, .job-title, [class*='title']")
        if title_el:
            result["title"] = (await title_el.inner_text()).strip()
    except Exception:
        pass

    # Wait for page to fully load (Cloudflare challenge may auto-resolve)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass  # Continue even if networkidle times out

    # Check for Cloudflare challenge and wait longer
    for sel in CAPTCHA_SELECTORS:
        if await page.query_selector(sel):
            print(f"  [GH] Cloudflare challenge detected, waiting up to 20s...")
            try:
                await page.wait_for_selector('#first_name, #application_form, form, .job-post', timeout=20000)
                print("  [GH] Challenge passed!")
            except Exception:
                # Try waiting more — sometimes Cloudflare just needs time
                await asyncio.sleep(5)
                if await page.query_selector('#first_name, form'):
                    print("  [GH] Challenge passed (delayed)!")
                else:
                    result["status"] = "captcha"
                    result["error"] = f"CAPTCHA blocked: {sel}"
                    return result
            break

    await screenshot("01_job_page")

    # Click Apply button if we're on the job description page (not the form yet)
    apply_selectors = [
        "a.btn--apply",
        "a[href*='#app']",
        "button:has-text('Apply for this job')",
        "button:has-text('Apply now')",
        "button:has-text('Apply')",
        "a:has-text('Apply for this job')",
        "a:has-text('Apply now')",
        "a:has-text('Apply')",
        ".postings-btn",
        "[data-test='apply-button']",
    ]
    for sel in apply_selectors:
        apply_btn = await page.query_selector(sel)
        if apply_btn:
            try:
                visible = await apply_btn.is_visible()
                if visible:
                    print(f"  [GH] Clicking Apply button ({sel})...")
                    await apply_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await apply_btn.click()
                    await asyncio.sleep(random.uniform(2, 3))
                    break
            except Exception:
                continue

    # Check for CAPTCHA again after clicking Apply
    for sel in CAPTCHA_SELECTORS:
        if await page.query_selector(sel):
            print(f"  [GH] Post-click challenge detected, waiting...")
            try:
                await page.wait_for_selector('#first_name, form', timeout=10000)
            except Exception:
                result["status"] = "captcha"
                result["error"] = f"CAPTCHA after Apply: {sel}"
                return result
            break

    await screenshot("02_apply_form")

    # --- FILL STANDARD FIELDS ---
    print("  [GH] Filling standard fields...")
    await _safe_fill(page, '#first_name', profile['first_name'])
    await _safe_fill(page, '#last_name', profile['last_name'])
    await _safe_fill(page, '#email', profile['email'])
    await _safe_fill(page, '#phone', profile['phone'])

    # Try LinkedIn field (various selectors)
    for sel in ['[autocomplete*="linkedin"]', '#job_application_answers_attributes_0_text_value',
                'input[name*="linkedin"]', 'input[placeholder*="LinkedIn"]']:
        if await _safe_fill(page, sel, profile['linkedin']):
            break

    # Try GitHub/website fields
    for sel in ['input[name*="github"]', 'input[placeholder*="GitHub"]',
                'input[name*="website"]', 'input[placeholder*="website"]',
                'input[name*="portfolio"]']:
        if await _safe_fill(page, sel, profile['github'] or profile['portfolio']):
            break

    await asyncio.sleep(random.uniform(0.5, 1))

    await screenshot("03_fields_filled")

    # --- UPLOAD RESUME ---
    print("  [GH] Uploading resume...")
    resume_input = await page.query_selector('input#resume[type="file"], input[name="resume"][type="file"]')
    if resume_input and Path(resume_pdf).exists():
        await resume_input.set_input_files(resume_pdf)
        await asyncio.sleep(2)  # wait for upload processing
        print("  [GH] Resume uploaded [OK]")
    else:
        print("  [GH] [WARN] Resume input not found or PDF missing")

    await screenshot("04_resume_uploaded")

    # --- HANDLE CUSTOM QUESTIONS ---
    print("  [GH] Scanning custom questions...")
    custom_questions = await _scan_custom_questions(page)
    print(f"  [GH] Found {len(custom_questions)} custom questions")

    # Phase 1: rule-based answers
    unanswered = []
    for q in custom_questions:
        answer = match_rule(q["text"], profile)
        if answer is not None:
            q["answer"] = answer
        else:
            unanswered.append(q)

    # Phase 2: LLM for remaining
    if unanswered:
        print(f"  [GH] Asking Gemini for {len(unanswered)} custom questions...")
        company = _extract_company(url)
        result["company"] = company
        llm_answers = answer_with_llm(unanswered, result["title"], company)
        for q in unanswered:
            q["answer"] = llm_answers.get(q["id"], "")

    # Phase 3: fill all answers
    for q in custom_questions:
        if q.get("answer"):
            await _fill_question(page, q)
            await asyncio.sleep(random.uniform(0.3, 0.7))

    # --- HANDLE DROPDOWNS (React Select) ---
    await _handle_react_selects(page, profile)

    await screenshot("05_questions_answered")

    await screenshot("06_ready_to_submit")

    # --- SAVE FULL FORM AS PDF (proof of what was submitted) ---
    try:
        safe_title = _safe_name(result.get('title', 'job'))
        pdf_name = f"gh_{safe_title}_form.pdf"
        pdf_path = SCREENSHOT_DIR / pdf_name
        await page.pdf(path=str(pdf_path), format="A4", print_background=True)
        result["form_pdf"] = str(pdf_path)
        print(f"  [GH] Form PDF saved: {pdf_path}")
    except Exception:
        # PDF only works in headless mode -- save full-page screenshot as fallback
        fallback = SCREENSHOT_DIR / f"gh_{_safe_name(result.get('title','job'))}_fullform.png"
        await page.screenshot(path=str(fallback), full_page=True)
        result["form_pdf"] = str(fallback)
        print(f"  [GH] Full-page screenshot saved (PDF requires headless): {fallback}")

    # Track which resume was used
    result["resume_used"] = resume_pdf

    # --- HANDLE MULTI-PAGE FORMS ---
    # Some Greenhouse forms have multiple pages with "Next" buttons
    page_num = 1
    while True:
        next_btn = await page.query_selector(
            'button:has-text("Next"), button:has-text("Continue"), '
            'input[value="Next"], a:has-text("Next Step")'
        )
        if not next_btn or not await next_btn.is_visible():
            break
        print(f"  [GH] Multi-page form detected, going to page {page_num + 1}...")
        await next_btn.click()
        await asyncio.sleep(random.uniform(2, 3))
        page_num += 1

        # Scan and fill questions on the new page
        new_questions = await _scan_custom_questions(page)
        if new_questions:
            print(f"  [GH] Page {page_num}: {len(new_questions)} more questions")
            for q in new_questions:
                answer = match_rule(q["text"], profile)
                if answer is not None:
                    q["answer"] = answer
                else:
                    # Quick LLM call for this page's questions
                    llm_answers = answer_with_llm([q], result["title"], result.get("company", ""))
                    q["answer"] = llm_answers.get(q["id"], "")
                if q.get("answer"):
                    await _fill_question(page, q)
                    await asyncio.sleep(random.uniform(0.3, 0.5))

            await _handle_react_selects(page, profile)
            await screenshot(f"page_{page_num}")

        if page_num > 10:  # Safety limit
            break

    # --- SUBMIT ---
    if dry_run:
        result["status"] = "dry_run"
        print("  [GH] DRY RUN — not submitting")
        return result

    submit_btn = await page.query_selector('#submit_app, button[type="submit"], input[type="submit"]')
    if submit_btn:
        print("  [GH] Submitting application...")
        await submit_btn.click()
        await asyncio.sleep(3)

        # Check for success
        page_text = await page.inner_text("body")
        if any(kw in page_text.lower() for kw in ["thank you", "application received", "submitted", "confirmation"]):
            result["status"] = "applied"
            print("  [GH] [OK] Application submitted!")
            await screenshot("07_confirmation")
        else:
            # Check for validation errors
            errors = await page.query_selector_all('.field--error, .error-message, [class*="error"]')
            if errors:
                error_texts = [await e.inner_text() for e in errors[:3]]
                result["error"] = "Validation errors: " + "; ".join(error_texts)
                print(f"  [GH] [FAIL] Validation errors: {result['error'][:100]}")
            else:
                result["status"] = "applied"  # Assume success if no errors
                print("  [GH] [OK] Submitted (no confirmation page detected)")
    else:
        result["error"] = "Submit button not found"
        print("  [GH] [FAIL] Submit button not found")

    return result


async def _safe_fill(page: Page, selector: str, value: str) -> bool:
    """Fill a field if it exists. Returns True if filled."""
    try:
        el = await page.query_selector(selector)
        if el and await el.is_visible():
            await el.fill(value)
            return True
    except Exception:
        pass
    return False


async def _scan_custom_questions(page: Page) -> list[dict]:
    """Scan the form for custom questions (not standard name/email/phone/resume)."""
    questions = []

    # Find all field containers
    fields = await page.query_selector_all('div.field, [class*="custom-question"], [class*="field"]')

    standard_ids = {"first_name", "last_name", "email", "phone", "resume", "cover_letter"}

    for field in fields:
        try:
            # Get the label
            label = await field.query_selector("label")
            if not label:
                continue
            label_text = (await label.inner_text()).strip()
            if not label_text or len(label_text) < 3:
                continue

            # Get the input element
            input_el = await field.query_selector("input, textarea, select")
            if not input_el:
                continue

            input_id = await input_el.get_attribute("id") or ""
            input_name = await input_el.get_attribute("name") or ""
            input_type = await input_el.get_attribute("type") or "text"
            tag = await input_el.evaluate("el => el.tagName.toLowerCase()")

            # Skip standard fields
            if input_id in standard_ids or input_name in standard_ids:
                continue
            if input_type == "file":
                continue

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
                "id": input_id or input_name,
                "text": label_text,
                "type": q_type,
                "selector": f"#{input_id}" if input_id else f"[name='{input_name}']",
            })
        except Exception:
            continue

    return questions


async def _fill_question(page: Page, question: dict):
    """Fill a single custom question based on its type."""
    sel = question["selector"]
    answer = question["answer"]
    q_type = question["type"]

    if not answer:
        return

    try:
        if q_type in ("text", "textarea"):
            await _safe_fill(page, sel, answer)
        elif q_type == "select":
            el = await page.query_selector(sel)
            if el:
                await el.select_option(label=answer)
        elif q_type == "radio":
            # Find the radio option matching the answer
            radios = await page.query_selector_all(f"input[name='{question['id']}']")
            for radio in radios:
                label = await radio.evaluate("el => el.closest('label')?.textContent?.trim() || el.value")
                if answer.lower() in label.lower():
                    await radio.click()
                    break
        elif q_type == "checkbox":
            el = await page.query_selector(sel)
            if el and answer.lower() in ("yes", "true", "1"):
                checked = await el.is_checked()
                if not checked:
                    await el.click()
    except Exception as e:
        print(f"  [GH] [WARN] Could not fill '{question['text'][:40]}': {e}")


async def _handle_react_selects(page: Page, profile: dict):
    """Handle React Select dropdowns (country, sponsorship, etc.)."""
    # Common React Select patterns in Greenhouse
    selects = await page.query_selector_all('[class*="select__control"]')

    for select in selects:
        try:
            # Get the label/placeholder
            container = await select.evaluate("el => el.closest('.field, [class*=field]')")
            if not container:
                continue

            # Try to get label text from parent
            label_el = await page.evaluate_handle(
                "(el) => el.closest('.field, [class*=field]')?.querySelector('label')",
                select
            )
            label_text = ""
            try:
                label_text = await label_el.evaluate("el => el?.textContent?.trim() || ''")
            except Exception:
                pass

            if not label_text:
                continue

            # Determine what to select based on label
            target_value = _get_select_value(label_text.lower(), profile)
            if not target_value:
                continue

            # Click to open, type to filter, click option
            await select.click()
            await asyncio.sleep(0.5)

            input_el = await page.query_selector('[class*="select__input"] input')
            if input_el:
                await input_el.fill(target_value)
                await asyncio.sleep(0.5)

            option = await page.query_selector('[class*="select__option"]')
            if option:
                await option.click()
                await asyncio.sleep(0.3)

        except Exception:
            continue


def _get_select_value(label: str, profile: dict) -> str:
    """Map a dropdown label to the target value."""
    if "country" in label:
        return profile["country"]
    if "sponsor" in label:
        return profile["require_sponsorship"]
    if "authorized" in label:
        return profile["authorized_to_work"]
    if "gender" in label:
        return "Decline"
    if "race" in label or "ethnic" in label:
        return "Decline"
    if "veteran" in label:
        return "not a protected"
    if "disability" in label or "disabled" in label:
        return "do not wish"
    if "state" in label or "province" in label:
        return profile["state"]
    return ""


def _extract_company(url: str) -> str:
    """Extract company name from Greenhouse URL."""
    # https://job-boards.greenhouse.io/companyname/jobs/123
    match = re.search(r"greenhouse\.io/([^/]+)", url)
    return match.group(1) if match else "company"
