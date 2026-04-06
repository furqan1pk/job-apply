"""Email verification code fetcher — polls Gmail for Workday/ATS verification codes.

Uses Gmail MCP when running inside Claude Code session,
or falls back to IMAP when running standalone.

Common verification email patterns:
- Workday: "Your verification code is: 123456"
- Greenhouse: rarely needs verification
- Lever: rarely needs verification
- iCIMS: "Please verify your email address"
"""

import re
import time
import json
import subprocess
from pathlib import Path


def get_verification_code_gmail_mcp(
    sender_patterns: list[str] = None,
    subject_patterns: list[str] = None,
    max_wait_seconds: int = 120,
    poll_interval: int = 10,
) -> str | None:
    """Poll Gmail via MCP for a verification code.

    This is designed to be called from within a Claude Code session
    where Gmail MCP tools are available. For standalone use, see
    get_verification_code_imap().

    Args:
        sender_patterns: email domains to search (e.g. ["workday", "myworkday"])
        subject_patterns: subject keywords (e.g. ["verification", "verify", "code"])
        max_wait_seconds: how long to poll before giving up
        poll_interval: seconds between polls

    Returns:
        Verification code string, or None if not found
    """
    if sender_patterns is None:
        sender_patterns = ["workday", "myworkdayjobs", "noreply"]
    if subject_patterns is None:
        subject_patterns = ["verification", "verify", "code", "confirm"]

    print(f"  [EMAIL] Polling Gmail for verification code (max {max_wait_seconds}s)...")

    # Build Gmail search query
    sender_query = " OR ".join(f"from:{s}" for s in sender_patterns)
    subject_query = " OR ".join(f"subject:{s}" for s in subject_patterns)
    query = f"({sender_query}) ({subject_query}) newer_than:5m"

    # This function is a template — actual Gmail MCP calls happen in the
    # adapter that calls this. See extract_code_from_text() for the parser.
    print(f"  [EMAIL] Search query: {query}")
    print(f"  [EMAIL] NOTE: Caller must use gmail_search_messages + gmail_read_message MCP tools")
    print(f"  [EMAIL] Then call extract_code_from_text() on the email body")

    return None  # Caller handles the actual MCP call


def extract_code_from_text(text: str) -> str | None:
    """Extract a verification code from email text.

    Handles common patterns:
    - "Your verification code is: 123456"
    - "Code: 123456"
    - "Enter this code: 123456"
    - "One-time passcode: 123456"
    - Just a 4-8 digit number on its own line
    """
    if not text:
        return None

    # Pattern 1: "code is: 123456" or "code: 123456"
    match = re.search(r"(?:code|passcode|otp|pin)\s*(?:is|:)\s*(\d{4,8})", text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: "verification code 123456"
    match = re.search(r"verification\s+code\s+(\d{4,8})", text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: standalone 6-digit number (most common)
    match = re.search(r"\b(\d{6})\b", text)
    if match:
        return match.group(1)

    # Pattern 4: "Enter 12345678"
    match = re.search(r"enter\s+(\d{4,8})", text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def get_verification_code_imap(
    email: str,
    app_password: str,
    sender_patterns: list[str] = None,
    max_wait_seconds: int = 120,
    poll_interval: int = 10,
) -> str | None:
    """Poll Gmail via IMAP for a verification code (standalone mode).

    Requires a Gmail App Password:
    1. Go to https://myaccount.google.com/apppasswords
    2. Generate an app password for "Mail"
    3. Store in credentials.json as "gmail_app_password"

    Args:
        email: Gmail address
        app_password: Gmail app password (NOT your regular password)
        sender_patterns: filter by sender
        max_wait_seconds: polling timeout
        poll_interval: seconds between checks

    Returns:
        Verification code or None
    """
    import imaplib
    import email as email_lib
    from datetime import datetime, timedelta

    if sender_patterns is None:
        sender_patterns = ["workday", "myworkdayjobs"]

    print(f"  [EMAIL] Polling Gmail IMAP for verification code...")

    start = time.time()
    while time.time() - start < max_wait_seconds:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email, app_password)
            mail.select("INBOX")

            # Search for recent emails
            since_date = (datetime.now() - timedelta(minutes=5)).strftime("%d-%b-%Y")
            _, message_ids = mail.search(None, f'(SINCE "{since_date}" UNSEEN)')

            for msg_id in message_ids[0].split()[-5:]:  # Last 5 unread
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                msg = email_lib.message_from_bytes(msg_data[0][1])

                sender = msg.get("From", "").lower()
                subject = msg.get("Subject", "").lower()

                # Check if from a relevant sender
                if not any(p in sender for p in sender_patterns):
                    continue

                # Get body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

                code = extract_code_from_text(body)
                if code:
                    print(f"  [EMAIL] Found code: {code} (from: {sender[:40]})")
                    mail.logout()
                    return code

            mail.logout()

        except Exception as e:
            print(f"  [EMAIL] IMAP error: {e}")

        print(f"  [EMAIL] No code yet, waiting {poll_interval}s...")
        time.sleep(poll_interval)

    print(f"  [EMAIL] No verification code found after {max_wait_seconds}s")
    return None


# --- Integration helper for workday adapter ---

async def wait_for_verification_code(portal_key: str, timeout: int = 120) -> str | None:
    """Wait for a verification code from a Workday portal signup.

    Tries Gmail MCP first (if in Claude session), then IMAP fallback.

    Args:
        portal_key: e.g. "amazon" — used to narrow email search
        timeout: max seconds to wait

    Returns:
        Code string or None
    """
    from credentials import _load

    creds_data = _load()

    # Try IMAP if app password is configured
    app_password = creds_data.get("gmail_app_password", "")
    email_addr = creds_data.get("default_email", "")

    if app_password and email_addr:
        return get_verification_code_imap(
            email=email_addr,
            app_password=app_password,
            sender_patterns=["workday", "myworkdayjobs", portal_key],
            max_wait_seconds=timeout,
        )

    # Fallback: print instructions for manual code entry
    print(f"\n  [EMAIL] Waiting for verification code from {portal_key}...")
    print(f"  [EMAIL] Check your email at {email_addr}")
    print(f"  [EMAIL] TIP: Add 'gmail_app_password' to credentials.json for auto-fetch")
    print(f"  [EMAIL] Or paste the code when prompted by workday_auto\n")

    return None
