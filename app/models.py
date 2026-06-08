"""SQLAlchemy models for projects and reports."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship

from .database import Base

if TYPE_CHECKING:
    from .models import Report


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, index=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    reports = relationship("Report", back_populates="project", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    total = Column(Integer)
    passed = Column(Integer)
    failed = Column(Integer)
    pass_rate = Column(Float)
    total_time_ms = Column(Float, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    raw_data = Column(JSON)

    project = relationship("Project", back_populates="reports")