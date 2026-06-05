from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
import json

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)


class TestUpload:
    def test_upload_file(self):
        data = {"project_name": "API-1", "summary": {"total": 10, "passed": 9, "failed": 1}, "results": []}
        files = {"file": ("r.json", json.dumps(data), "application/json")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 200
        assert resp.json()["pass_rate"] == 90.0

    def test_upload_text(self):
        data = {"project_name": "API-2", "summary": {"total": 5, "passed": 5, "failed": 0}, "results": []}
        resp = client.post("/api/upload-text", json=data)
        assert resp.status_code == 200
        assert resp.json()["pass_rate"] == 100.0

    def test_upload_same_project(self):
        data = {"project_name": "API-1", "summary": {"total": 4, "passed": 3, "failed": 1}, "results": []}
        files = {"file": ("r2.json", json.dumps(data), "application/json")}
        resp = client.post("/api/upload", files=files)
        assert resp.status_code == 200


class TestAPI:
    def test_list_projects(self):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_reports(self):
        resp = client.get("/api/projects/1/reports")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_report(self):
        resp = client.get("/api/reports/1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    def test_project_stats(self):
        resp = client.get("/api/projects/1/stats")
        assert resp.status_code == 200
        d = resp.json()
        assert len(d["labels"]) == 2
        assert len(d["pass_rates"]) == 2
        assert len(d["avg_times"]) == 2

    def test_delete_report(self):
        resp = client.delete("/api/reports/3")
        assert resp.status_code == 200

    def test_delete_project(self):
        resp = client.delete("/api/projects/2")
        assert resp.status_code == 200
        # Verify deleted
        resp2 = client.get("/api/projects")
        assert len(resp2.json()) == 1


class TestPages:
    def test_home(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "API-1" in resp.text

    def test_project_page(self):
        resp = client.get("/projects/1")
        assert resp.status_code == 200
        assert "Pass Rate Trend" in resp.text
        assert "Response Time Trend" in resp.text

    def test_report_page(self):
        resp = client.get("/reports/1")
        assert resp.status_code == 200
        assert "Report #1" in resp.text