"""Workday ATS adapter — wraps the workday_auto project (Selenium-based).

Workday is fundamentally different from Greenhouse/Lever:
- Multi-page React SPA (5-15 pages per application)
- Requires account creation (signup/signin per company)
- Custom questions per page, not all visible at once
- Heavy JavaScript, anti-bot measures
- Each employer has their own Workday tenant

This adapter delegates to the workday_auto project which handles all of this
with Selenium + sentence embeddings for question matching.

Setup:
    pip install selenium sentence-transformers nltk webdriver-manager
    Edit workday_auto/config/profile.yaml with your info
    Add Workday job URLs to workday_auto/config/jobs.txt

Usage from this tool:
    python apply.py --url https://company.wd5.myworkdayjobs.com/en-US/External/job/... --headed
"""

import subprocess
import sys
import time
import json
from pathlib import Path
from config import SCREENSHOT_DIR, load_profile

# Path to the cloned workday_auto repo
WORKDAY_AUTO_DIR = Path(__file__).parent.parent / "workday_auto"


async def apply(page, url: str, profile: dict, resume_pdf: str, dry_run: bool = False) -> dict:
    """Apply to a Workday job using the workday_auto Selenium wrapper.

    NOTE: This does NOT use the Playwright page — it spawns a separate
    Selenium process because Workday's multi-step forms are too complex
    to replicate in Playwright without the existing 2000-line Selenium code.
    """
    result = {"status": "failed", "error": "", "title": "", "company": "", "screenshots": []}

    if not WORKDAY_AUTO_DIR.exists():
        result["error"] = (
            f"workday_auto not found at {WORKDAY_AUTO_DIR}. "
            "Clone it: git clone https://github.com/amgenene/workday_auto.git"
        )
        print(f"  [WD] [FAIL] {result['error']}")
        return result

    # Extract company from Workday URL
    # Format: https://company.wd5.myworkdayjobs.com/...
    import re
    match = re.search(r"([\w-]+)\.wd\d+\.myworkdayjobs\.com", url)
    result["company"] = match.group(1) if match else "workday"

    # Write this URL to workday_auto's jobs.txt
    jobs_file = WORKDAY_AUTO_DIR / "config" / "jobs.txt"
    jobs_file.write_text(url + "\n", encoding="utf-8")

    # Sync our profile into workday_auto's profile.yaml
    _sync_profile(profile, resume_pdf)

    if dry_run:
        result["status"] = "dry_run"
        result["title"] = f"Workday job at {result['company']}"
        print(f"  [WD] DRY RUN -- would run workday_auto on {url}")
        print(f"  [WD] Profile synced to {WORKDAY_AUTO_DIR / 'config' / 'profile.yaml'}")
        return result

    # Run workday_auto as subprocess
    print(f"  [WD] Starting workday_auto for {result['company']}...")
    print(f"  [WD] This may take 2-5 minutes (multi-page form)...")

    try:
        proc = subprocess.run(
            [sys.executable, "workday.py"],
            cwd=str(WORKDAY_AUTO_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max
        )

        if proc.returncode == 0:
            result["status"] = "applied"
            result["title"] = f"Workday job at {result['company']}"
            print(f"  [WD] [OK] Workday application completed")
        else:
            result["error"] = proc.stderr[:200] if proc.stderr else "Unknown error"
            print(f"  [WD] [FAIL] {result['error'][:100]}")

        # Log stdout for debugging
        if proc.stdout:
            log_path = SCREENSHOT_DIR / f"workday_{result['company']}_log.txt"
            log_path.write_text(proc.stdout, encoding="utf-8")
            print(f"  [WD] Log saved: {log_path}")

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout (5 min) — Workday form may need manual intervention"
        print(f"  [WD] [FAIL] Timeout")
    except Exception as e:
        result["error"] = str(e)[:200]
        print(f"  [WD] [FAIL] {e}")

    return result


def _sync_profile(profile: dict, resume_pdf: str):
    """Write our profile data into workday_auto's profile.yaml format."""
    import yaml

    yaml_profile = {
        "email": profile["email"],
        "password": "",  # User must set this in workday_auto config
        "first_name": profile["first_name"],
        "family_name": profile["last_name"],
        "phone_number": profile["phone"],
        "address_line_1": profile["address"],
        "address_line_2": "",
        "address_line_3": "",
        "address_city": profile["city"],
        "address_state": profile["state"],
        "address_postal_code": profile["postal_code"],
        "resume_path": resume_pdf,
    }

    yaml_path = WORKDAY_AUTO_DIR / "config" / "profile.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_profile, f, default_flow_style=False)

    print(f"  [WD] Profile synced to {yaml_path}")
