# Test Report Dashboard

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![CI](https://github.com/dongjiaxi-cxk/test-report-dashboard/actions/workflows/tests.yml/badge.svg)](https://github.com/dongjiaxi-cxk/test-report-dashboard/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-20%20passed-brightgreen.svg)](tests/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)

**Web dashboard for tracking API test results over time.** Upload JSON test reports, visualize pass rate trends, compare runs, detect regressions.

```
docker compose up -d
# Open http://localhost:8000
```

## Why this exists

Running API contract tests is one thing — understanding trends is another. This dashboard:
- Tracks pass rates across multiple runs
- Visualizes response time trends with Chart.js
- Compares any two reports side-by-side
- Detects regressions automatically
- Exports data as CSV/JSON for further analysis

## Quick Start

### Docker (recommended)
```bash
docker compose up -d
```

### Manual
```bash
pip install -e .
uvicorn app.main:app --reload
```

Then open http://localhost:8000 and upload a JSON report.

## Features

| Feature | Description |
|---------|-------------|
| Upload | File upload or paste JSON directly |
| Dashboard | Project list with latest pass rates |
| Trends | Pass rate + response time line charts |
| Pagination | Browse large report histories |
| Search | Filter projects by name |
| Compare | Side-by-side diff of any two reports |
| Export | Download as CSV or JSON |
| Regression | Auto-detect pass rate drops |
| Docker | One-command deployment |
| FastAPI | Auto-generated OpenAPI docs at `/docs` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload` | Upload JSON report file |
| POST | `/api/upload-text` | Upload JSON via paste |
| GET | `/api/projects` | List projects (supports `?search=`) |
| GET | `/api/projects/{id}/reports` | List reports |
| GET | `/api/projects/{id}/stats` | Chart data (labels, pass_rates, avg_times) |
| GET | `/api/projects/{id}/export?fmt=csv` | Export as CSV/JSON |
| GET | `/api/projects/{id}/regression` | Regression check |
| GET | `/api/compare/{id1}/{id2}` | Compare two reports |
| DELETE | `/api/projects/{id}` | Delete project |
| DELETE | `/api/reports/{id}` | Delete report |

## Tech Stack

- **FastAPI** - Web framework
- **SQLAlchemy** + SQLite - ORM + database
- **Chart.js** - Interactive charts
- **Docker** - Containerized deployment

## Running Tests

```bash
pip install -e .
pytest tests/ -v
```

## License

MIT