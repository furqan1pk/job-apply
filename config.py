"""Configuration loader — profile, resume, env vars."""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env from ~/.applypilot/.env (reuse existing setup)
APPLYPILOT_DIR = Path.home() / ".applypilot"
load_dotenv(APPLYPILOT_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
RESUME_PDF = os.getenv("RESUME_PDF", str(Path.home() / "Downloads" / "Furqan Arshad Resume .pdf"))
RESUME_TXT = str(APPLYPILOT_DIR / "resume.txt")
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


def load_profile() -> dict:
    """Load profile from ~/.applypilot/profile.json and derive convenience fields."""
    path = APPLYPILOT_DIR / "profile.json"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")

    with open(path) as f:
        raw = json.load(f)

    personal = raw.get("personal", {})
    full_name = personal.get("full_name", "")
    parts = full_name.split(" ", 1)

    profile = {
        "full_name": full_name,
        "first_name": parts[0] if parts else "",
        "last_name": parts[1] if len(parts) > 1 else "",
        "email": personal.get("email", ""),
        "phone": personal.get("phone", "").replace("+1", "").replace("-", "").replace(" ", ""),
        "phone_raw": personal.get("phone", ""),
        "address": personal.get("address", ""),
        "city": personal.get("city", ""),
        "state": personal.get("province_state", ""),
        "country": personal.get("country", "United States"),
        "postal_code": personal.get("postal_code", ""),
        "linkedin": personal.get("linkedin_url", ""),
        "github": personal.get("github_url", ""),
        "portfolio": personal.get("portfolio_url", ""),
        "website": personal.get("website_url", ""),
        # Work authorization
        "authorized_to_work": raw.get("work_authorization", {}).get("legally_authorized_to_work", "Yes"),
        "require_sponsorship": raw.get("work_authorization", {}).get("require_sponsorship", "No"),
        # Compensation
        "salary": raw.get("compensation", {}).get("salary_expectation", ""),
        "salary_min": raw.get("compensation", {}).get("salary_range_min", ""),
        "salary_max": raw.get("compensation", {}).get("salary_range_max", ""),
        # Experience
        "years_experience": raw.get("experience", {}).get("years_of_experience_total", ""),
        "education": raw.get("experience", {}).get("education_level", ""),
        "current_title": raw.get("experience", {}).get("current_job_title", ""),
        "current_company": raw.get("experience", {}).get("current_company", ""),
        # EEO
        "gender": raw.get("eeo_voluntary", {}).get("gender", "Decline to self-identify"),
        "race": raw.get("eeo_voluntary", {}).get("race_ethnicity", "Decline to self-identify"),
        "veteran": raw.get("eeo_voluntary", {}).get("veteran_status", "I am not a protected veteran"),
        "disability": raw.get("eeo_voluntary", {}).get("disability_status", "I do not wish to answer"),
    }
    return profile


def load_resume_text() -> str:
    """Load resume as plain text."""
    if Path(RESUME_TXT).exists():
        return Path(RESUME_TXT).read_text(encoding="utf-8")
    return ""


def detect_platform(url: str) -> str:
    """Detect ATS platform from URL."""
    url_lower = url.lower()
    if "greenhouse.io" in url_lower:
        return "greenhouse"
    elif "lever.co" in url_lower:
        return "lever"
    elif "myworkdayjobs.com" in url_lower:
        return "workday"
    elif "linkedin.com/jobs" in url_lower:
        return "linkedin"
    elif "ashbyhq.com" in url_lower:
        return "ashby"
    elif "smartrecruiters.com" in url_lower:
        return "smartrecruiters"
    return "unknown"
