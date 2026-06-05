from pydantic import BaseModel
from datetime import datetime


class ReportUpload(BaseModel):
    project_name: str
    project_description: str = ""
    total: int
    passed: int
    failed: int
    total_time_ms: float = 0
    results: list = []


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    report_count: int = 0
    latest_pass_rate: float | None = None
    latest_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: int
    project_id: int
    total: int
    passed: int
    failed: int
    pass_rate: float
    total_time_ms: float
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ReportDetail(ReportOut):
    raw_data: dict | None = None