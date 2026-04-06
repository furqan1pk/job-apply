"""SQLite database layer — schema, CRUD, and query helpers."""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobs.db"
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT DEFAULT '',
            company TEXT DEFAULT '',
            platform TEXT DEFAULT '',
            score REAL DEFAULT 0,
            salary TEXT DEFAULT '',
            location TEXT DEFAULT '',
            resume_path TEXT DEFAULT '',
            status TEXT DEFAULT 'queued',
            error TEXT DEFAULT '',
            duration_sec REAL DEFAULT 0,
            screenshots TEXT DEFAULT '[]',
            form_pdf TEXT DEFAULT '',
            video_path TEXT DEFAULT '',
            resume_used TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            applied_at TEXT,
            attempts INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS apply_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            timestamp TEXT DEFAULT (datetime('now','localtime')),
            action TEXT,
            detail TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
    """)
    conn.commit()

    # Migrations — add columns if missing (for existing DBs)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    for col, default in [("form_pdf", "''"), ("video_path", "''"), ("resume_used", "''")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT DEFAULT {default}")
    conn.commit()


# --- CRUD ---

def add_job(url: str, title: str = "", company: str = "", platform: str = "",
            score: float = 0, salary: str = "", location: str = "",
            resume_path: str = "", notes: str = "") -> int:
    """Insert a job. Returns the job ID. Ignores duplicates."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO jobs (url, title, company, platform, score, salary, location, resume_path, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, title, company, platform, score, salary, location, resume_path, notes)
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # Duplicate URL
        row = conn.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
        return row["id"] if row else -1


def get_job(job_id: int) -> dict | None:
    """Get a single job by ID."""
    row = get_conn().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_jobs(status: str = None, platform: str = None, min_score: float = None,
             limit: int = 500) -> list[dict]:
    """List jobs with optional filters."""
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    if min_score is not None:
        query += " AND score >= ?"
        params.append(min_score)
    query += " ORDER BY score DESC, id DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_job(job_id: int, **kwargs):
    """Update specific fields on a job."""
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    get_conn().execute(f"UPDATE jobs SET {sets} WHERE id = ?", vals)
    get_conn().commit()


def delete_job(job_id: int):
    """Delete a job."""
    conn = get_conn()
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()


def reset_failed():
    """Reset all failed jobs back to queued."""
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = 'queued', error = '', attempts = attempts WHERE status = 'failed'")
    conn.commit()


def get_stats() -> dict:
    """Get aggregate stats."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    by_status = {}
    for row in conn.execute("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"):
        by_status[row["status"]] = row["cnt"]
    return {
        "total": total,
        "queued": by_status.get("queued", 0),
        "running": by_status.get("running", 0),
        "applied": by_status.get("applied", 0),
        "failed": by_status.get("failed", 0),
        "captcha": by_status.get("captcha", 0),
        "skipped": by_status.get("skipped", 0),
    }


def get_next_queued() -> dict | None:
    """Get the next queued job (highest score first)."""
    row = get_conn().execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY score DESC, id ASC LIMIT 1"
    ).fetchone()
    return _row_to_dict(row) if row else None


def add_log(job_id: int, action: str, detail: str = ""):
    """Add an entry to the apply log."""
    get_conn().execute(
        "INSERT INTO apply_log (job_id, action, detail) VALUES (?, ?, ?)",
        (job_id, action, detail)
    )
    get_conn().commit()


def get_logs(job_id: int = None, limit: int = 100) -> list[dict]:
    """Get log entries."""
    if job_id:
        rows = get_conn().execute(
            "SELECT * FROM apply_log WHERE job_id = ? ORDER BY id DESC LIMIT ?",
            (job_id, limit)
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM apply_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a dict, parsing JSON fields."""
    d = dict(row)
    # Parse screenshots JSON
    if isinstance(d.get("screenshots"), str):
        try:
            d["screenshots"] = json.loads(d["screenshots"])
        except (json.JSONDecodeError, TypeError):
            d["screenshots"] = []
    return d


# Auto-init on import
init_db()
