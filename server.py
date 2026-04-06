"""FastAPI server — API + background apply worker."""

import asyncio
import csv
import io
import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
from config import load_profile, detect_platform, RESUME_PDF, SCREENSHOT_DIR

app = FastAPI(title="Job Apply Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve screenshots as static files
SCREENSHOT_DIR.mkdir(exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOT_DIR)), name="screenshots")

# --- Background Worker State ---
_worker_state = {
    "running": False,
    "paused": False,
    "current_job": None,
    "total": 0,
    "completed": 0,
    "applied": 0,
    "failed": 0,
}
_worker_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)


# --- Pydantic Models ---

class AddJobRequest(BaseModel):
    url: str
    title: str = ""
    company: str = ""
    score: float = 0
    salary: str = ""
    location: str = ""
    resume_path: str = ""
    notes: str = ""


class ApplyRequest(BaseModel):
    dry_run: bool = False
    headed: bool = True
    min_score: float = 0
    status_filter: str = "queued"


# --- API Endpoints ---

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/jobs")
def list_jobs(
    status: str = None,
    platform: str = None,
    min_score: float = None,
    limit: int = 500,
):
    return db.get_jobs(status=status, platform=platform, min_score=min_score, limit=limit)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/add")
def add_job(req: AddJobRequest):
    platform = detect_platform(req.url)
    job_id = db.add_job(
        url=req.url, title=req.title, company=req.company,
        platform=platform, score=req.score, salary=req.salary,
        location=req.location, resume_path=req.resume_path, notes=req.notes,
    )
    return {"id": job_id, "platform": platform}


@app.post("/api/jobs/upload")
async def upload_csv(file: UploadFile = File(...)):
    """Upload a CSV/TSV of jobs. Auto-detects columns."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    # Detect delimiter
    delimiter = "\t" if "\t" in text.split("\n")[0] else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fields = [f.strip().lower() for f in (reader.fieldnames or [])]

    # Column mapping (flexible)
    col_map = {}
    for f in fields:
        fl = f.lower()
        if "url" in fl or "link" in fl or "apply" in fl:
            col_map["url"] = f
        elif fl in ("title", "job title", "role", "position"):
            col_map["title"] = f
        elif fl in ("company", "employer", "org"):
            col_map["company"] = f
        elif fl in ("score", "fit", "match"):
            col_map["score"] = f
        elif fl in ("salary", "pay", "compensation", "comp"):
            col_map["salary"] = f
        elif fl in ("location", "loc", "city"):
            col_map["location"] = f
        elif "platform" in fl or "ats" in fl or "source" in fl:
            col_map["platform"] = f
        elif "resume" in fl or "cv" in fl:
            col_map["resume_path"] = f
        elif "note" in fl:
            col_map["notes"] = f

    if "url" not in col_map:
        # Try to find URL in any column value
        raise HTTPException(400, f"No URL/link column found. Columns: {fields}")

    imported = 0
    skipped = 0
    for row in reader:
        url = row.get(col_map.get("url", ""), "").strip()
        if not url or not url.startswith("http"):
            skipped += 1
            continue

        platform = detect_platform(url)
        title = row.get(col_map.get("title", ""), "").strip()
        company = row.get(col_map.get("company", ""), "").strip()

        score_str = row.get(col_map.get("score", ""), "0").strip()
        try:
            score = float(score_str.replace("%", ""))
        except (ValueError, AttributeError):
            score = 0

        db.add_job(
            url=url,
            title=title,
            company=company,
            platform=platform,
            score=score,
            salary=row.get(col_map.get("salary", ""), "").strip(),
            location=row.get(col_map.get("location", ""), "").strip(),
            resume_path=row.get(col_map.get("resume_path", ""), "").strip(),
            notes=row.get(col_map.get("notes", ""), "").strip(),
        )
        imported += 1

    return {"imported": imported, "skipped": skipped, "columns_detected": col_map}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int):
    db.delete_job(job_id)
    return {"deleted": job_id}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int):
    db.update_job(job_id, status="queued", error="", attempts=0)
    return {"status": "queued"}


@app.post("/api/jobs/reset-failed")
def reset_failed():
    db.reset_failed()
    return {"status": "ok"}


@app.post("/api/jobs/clear-applied")
def clear_applied():
    conn = db.get_conn()
    conn.execute("DELETE FROM jobs WHERE status = 'applied'")
    conn.commit()
    return {"status": "ok"}


# --- Resume Upload ---

RESUME_DIR = Path("resumes")
RESUME_DIR.mkdir(exist_ok=True)


@app.post("/api/resumes/upload")
async def upload_resumes(files: list[UploadFile] = File(...)):
    """Upload multiple resume PDFs."""
    uploaded = []
    for f in files:
        content = await f.read()
        path = RESUME_DIR / f.filename
        path.write_bytes(content)
        uploaded.append({"name": f.filename, "path": str(path), "size": len(content)})
    return {"uploaded": uploaded}


@app.get("/api/resumes")
def list_resumes():
    """List all uploaded resumes."""
    resumes = []
    for p in RESUME_DIR.glob("*.pdf"):
        resumes.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    # Also check default resume
    default = Path(RESUME_PDF)
    if default.exists():
        resumes.insert(0, {"name": f"[DEFAULT] {default.name}", "path": str(default), "size": default.stat().st_size})
    return resumes


@app.post("/api/resumes/match")
def match_resumes():
    """Auto-match resumes to jobs by company name."""
    jobs = db.get_jobs()
    resumes = list(RESUME_DIR.glob("*.pdf"))
    matched = 0

    for job in jobs:
        if job.get("resume_path"):
            continue  # Already has a resume

        company = job.get("company", "").lower().replace(" ", "").replace("-", "")
        title = job.get("title", "").lower().replace(" ", "").replace("-", "")

        # Try to match by company name in filename
        best = None
        for r in resumes:
            rname = r.stem.lower().replace("_", "").replace("-", "")
            if company and company in rname:
                best = r
                break
            if title and any(word in rname for word in title.split() if len(word) > 3):
                best = r

        if best:
            db.update_job(job["id"], resume_path=str(best))
            matched += 1
        else:
            # Fall back to default resume
            db.update_job(job["id"], resume_path=RESUME_PDF)

    return {"matched": matched, "total": len(jobs)}


# --- Apply Worker ---

@app.get("/api/status")
def get_status():
    """Get current batch apply progress."""
    with _worker_lock:
        state = dict(_worker_state)
    state["stats"] = db.get_stats()
    return state


@app.post("/api/apply")
def start_apply(req: ApplyRequest):
    """Start batch apply in background."""
    with _worker_lock:
        if _worker_state["running"]:
            raise HTTPException(409, "Apply already running")

    queued = db.get_jobs(status=req.status_filter, min_score=req.min_score)
    if not queued:
        raise HTTPException(400, "No jobs in queue matching criteria")

    # Reset state
    with _worker_lock:
        _worker_state["running"] = True
        _worker_state["paused"] = False
        _worker_state["total"] = len(queued)
        _worker_state["completed"] = 0
        _worker_state["applied"] = 0
        _worker_state["failed"] = 0
        _worker_state["current_job"] = None

    # Launch worker in background
    _executor.submit(_run_batch, [j["id"] for j in queued], req.dry_run, req.headed)

    return {"status": "started", "total": len(queued)}


@app.post("/api/apply/pause")
def pause_apply():
    with _worker_lock:
        if _worker_state["running"]:
            _worker_state["paused"] = not _worker_state["paused"]
            return {"paused": _worker_state["paused"]}
    raise HTTPException(400, "Not running")


@app.post("/api/apply/cancel")
def cancel_apply():
    with _worker_lock:
        _worker_state["running"] = False
    return {"status": "cancelled"}


# --- Logs ---

@app.get("/api/logs")
def get_logs(job_id: int = None, limit: int = 100):
    return db.get_logs(job_id=job_id, limit=limit)


# --- Profile ---

@app.get("/api/profile")
def get_profile():
    try:
        return load_profile()
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/profile")
async def update_profile(profile: dict):
    """Save profile to ~/.applypilot/profile.json."""
    from config import APPLYPILOT_DIR
    path = APPLYPILOT_DIR / "profile.json"
    # Reconstruct the nested format
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    return {"status": "saved"}


# --- Stats ---

@app.get("/api/stats")
def get_stats():
    return db.get_stats()


# --- Background Worker ---

def _run_batch(job_ids: list[int], dry_run: bool, headed: bool):
    """Background thread: apply to jobs sequentially."""
    import asyncio

    # Import apply_single from the CLI module
    from apply import apply_single

    profile = load_profile()

    for job_id in job_ids:
        # Check if cancelled or paused
        with _worker_lock:
            if not _worker_state["running"]:
                break
            while _worker_state["paused"]:
                time.sleep(1)
                if not _worker_state["running"]:
                    return

        job = db.get_job(job_id)
        if not job:
            continue

        # Update state
        with _worker_lock:
            _worker_state["current_job"] = {
                "id": job["id"], "title": job["title"],
                "company": job["company"], "platform": job["platform"],
            }

        # Mark as running
        db.update_job(job_id, status="running")
        db.add_log(job_id, "started", f"dry_run={dry_run}")

        # Determine resume: job-specific > default
        resume = job.get("resume_path", "").strip()
        if not resume or not Path(resume).exists():
            resume = RESUME_PDF

        start = time.time()
        try:
            # Run the apply function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                apply_single(job["url"], profile, resume, dry_run, headed)
            )
            loop.close()

            duration = time.time() - start
            status = result.get("status", "failed")
            error = result.get("error", "")
            screenshots = json.dumps(result.get("screenshots", []))

            db.update_job(
                job_id,
                status=status,
                error=error,
                duration_sec=round(duration, 1),
                screenshots=screenshots,
                applied_at=datetime.now().isoformat() if status == "applied" else None,
                attempts=job.get("attempts", 0) + 1,
            )
            db.add_log(job_id, status, f"{duration:.1f}s | {error}" if error else f"{duration:.1f}s")

            with _worker_lock:
                _worker_state["completed"] += 1
                if status == "applied":
                    _worker_state["applied"] += 1
                elif status in ("failed", "captcha"):
                    _worker_state["failed"] += 1

        except Exception as e:
            duration = time.time() - start
            db.update_job(job_id, status="failed", error=str(e)[:300], duration_sec=round(duration, 1))
            db.add_log(job_id, "error", str(e)[:300])
            with _worker_lock:
                _worker_state["completed"] += 1
                _worker_state["failed"] += 1

        # Anti-bot delay
        import random
        time.sleep(random.uniform(3, 7))

    # Done
    with _worker_lock:
        _worker_state["running"] = False
        _worker_state["current_job"] = None


# Need datetime for the worker
from datetime import datetime


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8103)
