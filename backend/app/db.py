"""Simple JSON-file based store for MVP. Replace with SQLite/Postgres later."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
JOBS_FILE = DATA_DIR / "jobs.json"
RESULTS_DIR = DATA_DIR / "results"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_jobs() -> dict:
    if JOBS_FILE.exists():
        return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_jobs(jobs: dict):
    JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")


def save_job(job_id: str, filename: str, work_dir: str):
    jobs = _load_jobs()
    jobs[job_id] = {
        "id": job_id,
        "filename": filename,
        "work_dir": work_dir,
        "status": "pending",
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    _save_jobs(jobs)


def get_job(job_id: str) -> Optional[dict]:
    jobs = _load_jobs()
    return jobs.get(job_id)


def update_job_status(job_id: str, status: str, error: Optional[str] = None,
                      result_data: Optional[dict] = None):
    jobs = _load_jobs()
    if job_id not in jobs:
        return
    jobs[job_id]["status"] = status
    if error:
        jobs[job_id]["error"] = error
    if status in ("completed", "failed"):
        jobs[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
    if result_data:
        result_path = RESULTS_DIR / f"{job_id}.json"
        result_path.write_text(
            json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _save_jobs(jobs)


def get_job_result_data(job_id: str) -> Optional[dict]:
    result_path = RESULTS_DIR / f"{job_id}.json"
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    return None
