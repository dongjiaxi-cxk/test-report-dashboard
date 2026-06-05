# Test Report Dashboard

Web dashboard for managing and visualizing API test reports. Upload JSON reports, track pass rates over time, and drill into individual test results.

## Features

- Upload test reports via API or web UI
- Project-based organization
- Pass rate trend charts (Chart.js)
- Test result drill-down
- REST API

## Tech Stack

- **FastAPI** - async Python web framework
- **SQLAlchemy** - ORM with SQLite
- **Jinja2** - server-side templates
- **Chart.js** - pass rate trend visualization

## Quick Start

```bash
pip install -e .
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Upload a Report

```bash
curl -X POST http://127.0.0.1:8000/api/upload -F "file=@report.json"
```

Report format (compatible with [API Contract Tester](https://github.com/dongjiaxi-cxk/api-contract-tester)):

```json
{
    "project_name": "My API",
    "summary": {"total": 10, "passed": 9, "failed": 1},
    "results": [...]
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/projects | List projects |
| GET | /api/projects/{id}/reports | List reports |
| GET | /api/reports/{id} | Report detail |
| POST | /api/upload | Upload report |