"""Tests for v0.2.0 features: export, compare, pagination, search."""

import io, json
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, get_db
from app.models import Project, Report
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./test_v020.db"
test_engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine)

def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
Base.metadata.create_all(bind=test_engine)
client = TestClient(app)


class TestExport:
    def test_export_json(self):
        db = TestSession()
        proj = Project(name="export_test_json")
        db.add(proj)
        db.flush()
        r = Report(project_id=proj.id, total=5, passed=4, failed=1, pass_rate=80.0,
                   total_time_ms=100, raw_data={})
        db.add(r)
        db.commit()
        pid = proj.id

        resp = client.get(f"/api/projects/{pid}/export?fmt=json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project"] == "export_test_json"
        assert len(data["reports"]) == 1
        db.close()

    def test_export_csv(self):
        db = TestSession()
        proj = Project(name="export_test_csv")
        db.add(proj)
        db.flush()
        r = Report(project_id=proj.id, total=3, passed=2, failed=1, pass_rate=66.7,
                   total_time_ms=50, raw_data={})
        db.add(r)
        db.commit()
        pid = proj.id

        resp = client.get(f"/api/projects/{pid}/export?fmt=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "export_test_csv" in resp.headers.get("content-disposition", "")
        db.close()


class TestCompare:
    def test_compare_api(self):
        db = TestSession()
        proj = Project(name="compare_test")
        db.add(proj)
        db.flush()
        r1 = Report(project_id=proj.id, total=10, passed=8, failed=2, pass_rate=80.0,
                    total_time_ms=200, raw_data={})
        r2 = Report(project_id=proj.id, total=10, passed=9, failed=1, pass_rate=90.0,
                    total_time_ms=150, raw_data={})
        db.add_all([r1, r2])
        db.commit()
        aid, bid = r1.id, r2.id

        resp = client.get(f"/api/compare/{aid}/{bid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["delta"]["pass_rate"] == 10.0
        assert data["delta"]["total_time_ms"] == -50.0
        db.close()

    def test_compare_page(self):
        db = TestSession()
        proj = Project(name="compare_page_test")
        db.add(proj)
        db.flush()
        r1 = Report(project_id=proj.id, total=5, passed=3, failed=2, pass_rate=60.0,
                    total_time_ms=300, raw_data={})
        r2 = Report(project_id=proj.id, total=5, passed=4, failed=1, pass_rate=80.0,
                    total_time_ms=250, raw_data={})
        db.add_all([r1, r2])
        db.commit()

        resp = client.get(f"/compare/{r1.id}/{r2.id}")
        assert resp.status_code == 200
        assert "Compare Reports" in resp.text
        assert "+20.0" in resp.text or "20.0" in resp.text
        db.close()


class TestSearch:
    def test_search_projects_api(self):
        db = TestSession()
        proj = Project(name="unique_search_project")
        db.add(proj)
        db.commit()

        resp = client.get("/api/projects?search=unique_search")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "unique_search_project"
        db.close()

    def test_search_no_results(self):
        resp = client.get("/api/projects?search=zzz_nonexistent_zzz")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_page(self):
        db = TestSession()
        proj = Project(name="search_page_display")
        db.add(proj)
        db.commit()

        resp = client.get("/?search=search_page")
        assert resp.status_code == 200
        assert "search_page_display" in resp.text
        db.close()


class TestPagination:
    def test_project_page_with_page_param(self):
        db = TestSession()
        proj = Project(name="paginated_project")
        db.add(proj)
        db.flush()
        for i in range(5):
            db.add(Report(project_id=proj.id, total=1, passed=1, failed=0,
                         pass_rate=100.0, total_time_ms=10, raw_data={}))
        db.commit()

        resp = client.get(f"/projects/{proj.id}?page=1")
        assert resp.status_code == 200
        assert "paginated_project" in resp.text
        db.close()


def teardown_module():
    import os, time
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    for _ in range(3):
        try:
            os.unlink("test_v020.db")
            break
        except PermissionError:
            time.sleep(0.1)