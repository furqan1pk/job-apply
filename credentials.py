"""Credentials manager — persistent login storage for job portals.

Stores per-portal credentials in ~/.applypilot/credentials.json.
Auto-creates accounts on first visit, saves for reuse.

File format:
{
  "default_email": "you@email.com",
  "default_password": "YourPassword123!",
  "portals": {
    "amazon": {
      "email": "you@email.com",
      "password": "YourPassword123!",
      "created_at": "2026-04-05T18:30:00",
      "last_used": "2026-04-05T18:30:00",
      "status": "active"
    }
  }
}
"""

import json
from datetime import datetime
from pathlib import Path

CREDS_PATH = Path.home() / ".applypilot" / "credentials.json"


def _load() -> dict:
    """Load credentials file."""
    if CREDS_PATH.exists():
        with open(CREDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"default_email": "", "default_password": "", "portals": {}}


def _save(data: dict):
    """Save credentials file."""
    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_credentials(portal_key: str) -> dict:
    """Get credentials for a portal. Falls back to defaults if no portal-specific creds.

    Args:
        portal_key: e.g. "amazon", "microsoft", "meta" (extracted from Workday URL)

    Returns:
        {"email": str, "password": str, "is_new": bool}
    """
    data = _load()
    portal_key = portal_key.lower().strip()

    # Check for portal-specific credentials
    if portal_key in data.get("portals", {}):
        portal = data["portals"][portal_key]
        # Update last_used
        portal["last_used"] = datetime.now().isoformat()
        _save(data)
        return {
            "email": portal.get("email", data.get("default_email", "")),
            "password": portal.get("password", data.get("default_password", "")),
            "is_new": False,
        }

    # No portal-specific creds — use defaults (this is a new portal)
    return {
        "email": data.get("default_email", ""),
        "password": data.get("default_password", ""),
        "is_new": True,
    }


def save_portal_credentials(portal_key: str, email: str, password: str, status: str = "active"):
    """Save credentials after successful signup/signin.

    Args:
        portal_key: e.g. "amazon"
        email: email used
        password: password used
        status: "active", "signup_failed", "signin_failed"
    """
    data = _load()
    portal_key = portal_key.lower().strip()

    if "portals" not in data:
        data["portals"] = {}

    data["portals"][portal_key] = {
        "email": email,
        "password": password,
        "created_at": datetime.now().isoformat(),
        "last_used": datetime.now().isoformat(),
        "status": status,
    }
    _save(data)
    print(f"  [CRED] Saved credentials for '{portal_key}' (status: {status})")


def list_portals() -> list[dict]:
    """List all saved portal credentials (without exposing passwords)."""
    data = _load()
    result = []
    for key, portal in data.get("portals", {}).items():
        result.append({
            "portal": key,
            "email": portal.get("email", ""),
            "status": portal.get("status", "unknown"),
            "created_at": portal.get("created_at", ""),
            "last_used": portal.get("last_used", ""),
        })
    return result


def has_password() -> bool:
    """Check if a default password is configured."""
    data = _load()
    return bool(data.get("default_password", "").strip())
