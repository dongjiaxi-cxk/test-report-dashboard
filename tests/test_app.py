from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import Project, Report
import json, os

# Recreate tables for testing
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)

SAMPLE_DIR = os.path.dirname(__file__)


class TestUploadReport:
    def test_upload_creates_project(self):
        data = {
            "project_name": "Test Project",
            "summary": {"total": 10, "passed": 9, "failed": 1},
            "results": [{"name": "t1", "passed": True}]
        }
        files = {"file": ("report.json", json.dumps(data), "application/json")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 200
        assert resp.json()["project"] == "Test Project"
        assert resp.json()["pass_rate"] == 90.0

    def test_upload_same_project(self):
        data = {
            "project_name": "Test Project",
            "summary": {"total": 5, "passed": 5, "failed": 0},
            "results": []
        }
        files = {"file": ("report2.json", json.dumps(data), "application/json")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 200


class TestAPI:
    def test_list_projects(self):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) >= 1
        assert projects[0]["name"] == "Test Project"
        assert projects[0]["report_count"] == 2

    def test_list_reports(self):
        resp = client.get("/api/projects/1/reports")
        assert resp.status_code == 200
        reports = resp.json()
        assert len(reports) == 2

    def test_get_report(self):
        resp = client.get("/api/reports/1")
        assert resp.status_code == 200
        report = resp.json()
        assert report["total"] == 10
        assert report["passed"] == 9


class TestPages:
    def test_home_page(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Test Project" in resp.text

    def test_project_page(self):
        resp = client.get("/projects/1")
        assert resp.status_code == 200
        assert "Test Project" in resp.text
        assert "Pass Rate Trend" in resp.text

    def test_report_page(self):
        resp = client.get("/reports/1")
        assert resp.status_code == 200
        assert "Report #1" in resp.text