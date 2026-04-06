"""Workday ATS adapter — wraps workday_auto (Selenium) with credential management.

Workday is fundamentally different from Greenhouse/Lever:
- Multi-page React SPA (5-15 pages per application)
- Requires account creation (signup/signin per company)
- Custom questions per page, not all visible at once
- Each employer has their own Workday tenant

Flow:
1. Check credentials.json for existing portal login
2. If new portal: auto-create account with default email/password
3. If existing portal: sign in with saved credentials
4. Run workday_auto for multi-step form filling
5. Save credentials on success for reuse

Setup:
    pip install selenium sentence-transformers nltk webdriver-manager pyyaml
    Set default_password in ~/.applypilot/credentials.json
"""

import re
import subprocess
import sys
from pathlib import Path

from config import SCREENSHOT_DIR
from credentials import get_credentials, save_portal_credentials, has_password

# Path to the cloned workday_auto repo (sibling directory)
WORKDAY_AUTO_DIR = Path(__file__).parent.parent / "workday_auto"


def _extract_portal_key(url: str) -> str:
    """Extract company/portal key from Workday URL.

    Examples:
        https://amazon.wd5.myworkdayjobs.com/... -> amazon
        https://microsoft.wd1.myworkdayjobs.com/... -> microsoft
        https://meta.wd1.myworkdayjobs.com/... -> meta
    """
    match = re.search(r"([\w-]+)\.wd\d+\.myworkdayjobs\.com", url)
    return match.group(1).lower() if match else "workday"


async def apply(page, url: str, profile: dict, resume_pdf: str, dry_run: bool = False) -> dict:
    """Apply to a Workday job.

    Handles account creation automatically:
    - First visit to a portal: creates account with default credentials
    - Return visits: signs in with saved credentials
    - Credentials stored in ~/.applypilot/credentials.json
    """
    result = {"status": "failed", "error": "", "title": "", "company": "", "screenshots": []}

    # --- VALIDATE SETUP ---
    if not WORKDAY_AUTO_DIR.exists():
        result["error"] = (
            f"workday_auto not found at {WORKDAY_AUTO_DIR}. "
            "Run: git clone https://github.com/amgenene/workday_auto.git "
            f"into {WORKDAY_AUTO_DIR.parent}"
        )
        print(f"  [WD] [FAIL] {result['error']}")
        return result

    if not has_password():
        result["error"] = (
            "No default password set in ~/.applypilot/credentials.json. "
            "Set 'default_password' before applying to Workday portals."
        )
        print(f"  [WD] [FAIL] {result['error']}")
        return result

    # --- EXTRACT PORTAL INFO ---
    portal_key = _extract_portal_key(url)
    result["company"] = portal_key
    result["title"] = f"Workday job at {portal_key}"

    # --- GET CREDENTIALS ---
    creds = get_credentials(portal_key)
    if creds["is_new"]:
        print(f"  [WD] New portal '{portal_key}' -- will auto-create account")
        print(f"  [WD] Email: {creds['email']}")
    else:
        print(f"  [WD] Known portal '{portal_key}' -- will sign in")
        print(f"  [WD] Email: {creds['email']}")

    # --- SYNC PROFILE + CREDENTIALS TO WORKDAY_AUTO ---
    _sync_config(profile, resume_pdf, creds, url)

    if dry_run:
        result["status"] = "dry_run"
        print(f"  [WD] DRY RUN -- config synced, would run workday_auto")
        print(f"  [WD] Account action: {'SIGNUP' if creds['is_new'] else 'SIGNIN'}")
        return result

    # --- RUN WORKDAY_AUTO ---
    print(f"  [WD] Starting workday_auto for '{portal_key}'...")
    print(f"  [WD] This may take 2-5 minutes (multi-page form)...")

    try:
        proc = subprocess.run(
            [sys.executable, "workday.py"],
            cwd=str(WORKDAY_AUTO_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max
            encoding="utf-8",
            errors="replace",
        )

        # Save log
        log_path = SCREENSHOT_DIR / f"workday_{portal_key}_log.txt"
        log_content = f"=== STDOUT ===\n{proc.stdout or ''}\n\n=== STDERR ===\n{proc.stderr or ''}"
        log_path.write_text(log_content, encoding="utf-8")
        print(f"  [WD] Log saved: {log_path}")

        if proc.returncode == 0:
            result["status"] = "applied"
            # Save credentials on success
            save_portal_credentials(portal_key, creds["email"], creds["password"], "active")
            print(f"  [WD] [OK] Application completed")
        else:
            # Check if it was an account issue
            stderr = proc.stderr or ""
            stdout = proc.stdout or ""
            combined = stderr + stdout

            if "already exists" in combined or "already in use" in combined:
                # Account exists but wrong password — mark it
                save_portal_credentials(portal_key, creds["email"], creds["password"], "password_mismatch")
                result["error"] = "Account exists but login failed — check password"
            elif "Signup failed" in combined:
                save_portal_credentials(portal_key, creds["email"], creds["password"], "signup_failed")
                result["error"] = "Could not create account"
            else:
                result["error"] = (stderr[:200] if stderr else "Unknown error")

            print(f"  [WD] [FAIL] {result['error'][:100]}")

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout (5 min) -- may need manual intervention"
        save_portal_credentials(portal_key, creds["email"], creds["password"], "timeout")
        print(f"  [WD] [FAIL] Timeout")
    except Exception as e:
        result["error"] = str(e)[:200]
        print(f"  [WD] [FAIL] {e}")

    return result


def _sync_config(profile: dict, resume_pdf: str, creds: dict, job_url: str):
    """Sync profile + credentials into workday_auto's config files."""
    import yaml

    # --- profile.yaml ---
    yaml_profile = {
        "email": creds["email"],
        "password": creds["password"],
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

    config_dir = WORKDAY_AUTO_DIR / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = config_dir / "profile.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_profile, f, default_flow_style=False)

    # --- jobs.txt ---
    jobs_path = config_dir / "jobs.txt"
    jobs_path.write_text(job_url + "\n", encoding="utf-8")

    # --- companies.txt (track known portals) ---
    portal_key = _extract_portal_key(job_url)
    companies_path = config_dir / "companies.txt"
    existing = set()
    if companies_path.exists():
        existing = set(companies_path.read_text(encoding="utf-8").strip().split("\n"))
    if portal_key not in existing:
        with open(companies_path, "a", encoding="utf-8") as f:
            f.write(portal_key + "\n")

    print(f"  [WD] Config synced: profile + jobs + companies")
