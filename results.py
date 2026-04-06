"""Results logger — CSV + JSONL output."""

import csv
import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def log_result(
    url: str,
    platform: str,
    status: str,
    duration_sec: float = 0,
    error: str = "",
    job_title: str = "",
    company: str = "",
):
    """Log application result to CSV and JSONL."""
    timestamp = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y-%m-%d")

    row = {
        "timestamp": timestamp,
        "url": url,
        "platform": platform,
        "job_title": job_title,
        "company": company,
        "status": status,
        "duration_sec": round(duration_sec, 1),
        "error": error,
    }

    # CSV
    csv_path = RESULTS_DIR / f"applications_{date_str}.csv"
    is_new = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if is_new:
            writer.writeheader()
        writer.writerow(row)

    # JSONL
    jsonl_path = RESULTS_DIR / f"applications_{date_str}.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    # Console
    icons = {"applied": "[OK]", "failed": "[FAIL]", "captcha": "[CAPTCHA]", "skipped": "[SKIP]", "dry_run": "[DRY]"}.get(status, "[?]")
    print(f"  {icons} {status.upper()} | {job_title or url} | {duration_sec:.0f}s")
