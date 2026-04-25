import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from typing import Optional

from .config import settings
from .ocr_engine import pdf_to_ocr
from .extractor import extract_contract_data, extract_survey_data
from .db import get_job, save_job, update_job_status, get_job_result_data

security = HTTPBearer(auto_error=False)
app = FastAPI(title=settings.app_name, version="0.1.0")

UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def verify_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials


# ── API Routes ──────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    bg: BackgroundTasks = BackgroundTasks(),
    _=Depends(verify_api_key),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    job_id = uuid.uuid4().hex[:12]
    save_dir = UPLOAD_DIR / job_id
    save_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = save_dir / file.filename
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.max_upload_mb}MB)")
    pdf_path.write_bytes(content)

    save_job(job_id, file.filename, str(save_dir))
    bg.add_task(_process_job_async, job_id, str(pdf_path), str(save_dir))

    return {"job_id": job_id, "status": "processing", "filename": file.filename}


@app.get("/api/job/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job["id"],
        "status": job["status"],
        "filename": job["filename"],
        "error": job["error"],
    }


@app.get("/api/job/{job_id}/result")
def get_job_result(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job is {job['status']}, not completed yet")
    data = get_job_result_data(job_id)
    return {"job_id": job_id, "status": "completed", "data": data}


@app.get("/api/job/{job_id}/download/{fmt}")
def download_result(job_id: str, fmt: str, _=Depends(verify_api_key)):
    if fmt not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="Format must be 'csv' or 'json'")
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    data = get_job_result_data(job_id)

    if fmt == "json":
        content = json.dumps(data, ensure_ascii=False, indent=2)
        media = "application/json"
        ext = "json"
    else:
        import csv, io
        buf = io.StringIO()
        if data and isinstance(data, dict):
            writer = csv.DictWriter(buf, fieldnames=list(data.keys()))
            writer.writeheader()
            flat = {}
            for k, v in data.items():
                flat[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
            writer.writerow(flat)
        content = buf.getvalue()
        media = "text/csv; charset=utf-8"
        ext = "csv"

    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{job_id}.{ext}"'},
    )


# ── Background Processing ───────────────────────────────────

def _process_job_async(job_id: str, pdf_path: str, work_dir: str):
    """Run extraction synchronously; swap to background worker when scaling."""
    try:
        update_job_status(job_id, "processing")
        texts = pdf_to_ocr(pdf_path, work_dir=work_dir, all_pages=True)
        if not texts:
            update_job_status(job_id, "failed", "No text could be extracted from PDF")
            return
        result = {"filename": Path(pdf_path).name}
        result.update(extract_contract_data(texts))
        result.update(extract_survey_data(texts))
        update_job_status(job_id, "completed", result_data=result)
    except Exception as e:
        update_job_status(job_id, "failed", str(e))


# ── Serve Static Frontend ───────────────────────────────────

STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ContractSaaS</h1><p>Frontend not found</p>")


@app.get("/app.js")
def app_js():
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/style.css")
def style_css():
    return FileResponse(STATIC_DIR / "style.css", media_type="text/css")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
