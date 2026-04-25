from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class JobCreate(BaseModel):
    pass


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    filename: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class JobResult(BaseModel):
    job_id: str
    status: str
    data: Optional[dict] = None
