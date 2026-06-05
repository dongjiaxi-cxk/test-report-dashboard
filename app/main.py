from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import json, os

from .database import engine, get_db, Base
from .models import Project, Report
from .schemas import ProjectOut, ReportOut, ReportDetail

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Test Report Dashboard")

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ─── API Routes ───────────────────────────────────────────────────

@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    """List all projects with latest report stats."""
    projects = db.query(Project).all()
    result = []
    for p in projects:
        latest = db.query(Report).filter(Report.project_id == p.id).order_by(desc(Report.uploaded_at)).first()
        count = db.query(Report).filter(Report.project_id == p.id).count()
        result.append(ProjectOut(
            id=p.id,
            name=p.name,
            description=p.description or "",
            report_count=count,
            latest_pass_rate=latest.pass_rate if latest else None,
            latest_at=latest.uploaded_at if latest else None,
        ))
    return result


@app.get("/api/projects/{project_id}/reports")
def list_reports(project_id: int, db: Session = Depends(get_db)):
    """List reports for a project."""
    reports = db.query(Report).filter(Report.project_id == project_id).order_by(desc(Report.uploaded_at)).all()
    return reports


@app.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    """Get report detail with raw data."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return {"error": "Not found"}
    return ReportDetail(
        id=report.id,
        project_id=report.project_id,
        total=report.total,
        passed=report.passed,
        failed=report.failed,
        pass_rate=report.pass_rate,
        total_time_ms=report.total_time_ms or 0,
        uploaded_at=report.uploaded_at,
        raw_data=report.raw_data,
    )


@app.post("/api/upload")
async def upload_report(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a JSON test report."""
    content = await file.read()
    data = json.loads(content)

    project_name = data.get("project_name", file.filename.rsplit(".", 1)[0])
    summary = data.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0
    total_time_ms = data.get("total_time_ms", 0)

    # Get or create project
    project = db.query(Project).filter(Project.name == project_name).first()
    if not project:
        project = Project(name=project_name)
        db.add(project)
        db.flush()

    report = Report(
        project_id=project.id,
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        total_time_ms=total_time_ms,
        raw_data=data,
    )
    db.add(report)
    db.commit()

    return {"id": report.id, "project": project_name, "pass_rate": pass_rate}


# ─── Frontend Pages ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(db: Session = Depends(get_db)):
    """Home page - project list."""
    projects = db.query(Project).all()
    rows = ""
    for p in projects:
        count = db.query(Report).filter(Report.project_id == p.id).count()
        latest = db.query(Report).filter(Report.project_id == p.id).order_by(desc(Report.uploaded_at)).first()
        rate = f"{latest.pass_rate}%" if latest else "-"
        color = "#22c55e" if latest and latest.pass_rate >= 90 else ("#ef4444" if latest else "#888")
        date_str = latest.uploaded_at.strftime("%Y-%m-%d %H:%M") if latest else "-"
        rows += f"""
        <tr>
            <td><a href="/projects/{p.id}">{p.name}</a></td>
            <td>{p.description or ""}</td>
            <td>{count}</td>
            <td><span style="color:{color};font-weight:bold">{rate}</span></td>
            <td>{date_str}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Test Report Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
nav {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px 40px; display:flex; justify-content:space-between; align-items:center; }}
nav h1 {{ font-size: 20px; }}
nav a {{ color: white; text-decoration: none; margin-left: 20px; opacity: 0.9; }}
nav a:hover {{ opacity: 1; }}
.container {{ max-width: 1000px; margin: 30px auto; padding: 0 20px; }}
.card {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 20px; }}
.card h2 {{ margin-bottom: 16px; font-size: 18px; }}
form {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
input[type="file"] {{ padding: 8px; border: 1px solid #ddd; border-radius: 6px; }}
button {{ background: #667eea; color: white; border: none; padding: 10px 24px; border-radius: 6px; cursor: pointer; font-size: 14px; }}
button:hover {{ background: #5a6fd6; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 12px 16px; border-bottom: 1px solid #f1f5f9; }}
th {{ font-size: 12px; text-transform: uppercase; color: #888; }}
td {{ font-size: 14px; }}
td a {{ color: #667eea; text-decoration: none; }}
td a:hover {{ text-decoration: underline; }}
#status {{ margin-top: 10px; font-size: 14px; }}
</style>
</head>
<body>
<nav>
    <h1>Test Report Dashboard</h1>
    <div><a href="/api/projects">API</a></div>
</nav>
<div class="container">
    <div class="card">
        <h2>Upload Report</h2>
        <form id="uploadForm" enctype="multipart/form-data">
            <input type="file" id="file" name="file" accept=".json">
            <button type="submit">Upload</button>
        </form>
        <div id="status"></div>
    </div>
    <div class="card">
        <h2>Projects</h2>
        <table>
        <thead><tr><th>Project</th><th>Description</th><th>Reports</th><th>Latest Pass Rate</th><th>Last Run</th></tr></thead>
        <tbody>{rows}</tbody>
        </table>
    </div>
</div>
<script>
document.getElementById('uploadForm').addEventListener('submit', async (e) => {{
    e.preventDefault();
    const formData = new FormData();
    formData.append('file', document.getElementById('file').files[0]);
    const resp = await fetch('/api/upload', {{ method: 'POST', body: formData }});
    const data = await resp.json();
    document.getElementById('status').textContent = 'Uploaded! Pass rate: ' + data.pass_rate + '%';
    setTimeout(() => location.reload(), 1000);
}});
</script>
</body>
</html>"""
    return html


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: int, db: Session = Depends(get_db)):
    """Project detail page with report list and trend chart."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return HTMLResponse("<h2>Not Found</h2>", status_code=404)

    reports = db.query(Report).filter(Report.project_id == project_id).order_by(Report.uploaded_at).all()

    # Build table rows
    rows = ""
    for r in reversed(reports):
        color = "#22c55e" if r.pass_rate >= 90 else ("#ef4444" if r.pass_rate < 80 else "#f59e0b")
        rows += f"""
        <tr>
            <td><a href="/reports/{r.id}">{r.uploaded_at.strftime("%Y-%m-%d %H:%M")}</a></td>
            <td>{r.total}</td>
            <td style="color:#22c55e">{r.passed}</td>
            <td style="color:#ef4444">{r.failed}</td>
            <td><span style="color:{color};font-weight:bold">{r.pass_rate}%</span></td>
            <td>{r.total_time_ms:.0f}ms</td>
        </tr>"""

    # Trend data for chart
    labels = [r.uploaded_at.strftime("%m-%d") for r in reports]
    rates = [r.pass_rate for r in reports]
    latest_rate = rates[-1] if rates else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project.name} - Test Report Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
nav {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px 40px; display:flex; justify-content:space-between; align-items:center; }}
nav h1 {{ font-size: 20px; }}
nav a {{ color: white; text-decoration: none; opacity: 0.9; }}
nav a:hover {{ opacity: 1; }}
.container {{ max-width: 1000px; margin: 30px auto; padding: 0 20px; }}
.stats {{ display: flex; gap: 15px; margin-bottom: 20px; }}
.stat {{ flex:1; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
.stat .num {{ font-size: 28px; font-weight: bold; }}
.stat .label {{ color: #888; font-size: 13px; margin-top: 4px; }}
.card {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 20px; }}
.card h2 {{ margin-bottom: 16px; font-size: 18px; }}
canvas {{ max-width: 100%; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 12px 16px; border-bottom: 1px solid #f1f5f9; }}
th {{ font-size: 12px; text-transform: uppercase; color: #888; }}
td {{ font-size: 14px; }}
td a {{ color: #667eea; text-decoration: none; }}
td a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<nav>
    <h1><a href="/">Test Report Dashboard</a> / {project.name}</h1>
</nav>
<div class="container">
    <div class="stats">
        <div class="stat"><div class="num" style="color:#667eea">{len(reports)}</div><div class="label">Total Reports</div></div>
        <div class="stat"><div class="num" style="color:#22c55e">{latest_rate:.0f}%</div><div class="label">Latest Pass Rate</div></div>
    </div>
    <div class="card">
        <h2>Pass Rate Trend</h2>
        <canvas id="trendChart"></canvas>
    </div>
    <div class="card">
        <h2>Reports</h2>
        <table>
        <thead><tr><th>Date</th><th>Total</th><th>Passed</th><th>Failed</th><th>Rate</th><th>Time</th></tr></thead>
        <tbody>{rows}</tbody>
        </table>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
new Chart(document.getElementById('trendChart'), {{
    type: 'line',
    data: {{
        labels: {labels},
        datasets: [{{
            label: 'Pass Rate %',
            data: {rates},
            borderColor: '#667eea',
            backgroundColor: 'rgba(102,126,234,0.1)',
            fill: true,
            tension: 0.3
        }}]
    }},
    options: {{
        scales: {{ y: {{ min: 0, max: 100 }} }}
    }}
}});
</script>
</body>
</html>"""
    return html


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(report_id: int, db: Session = Depends(get_db)):
    """Single report detail page."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return HTMLResponse("<h2>Not Found</h2>", status_code=404)

    project = db.query(Project).filter(Project.id == report.project_id).first()
    color = "#22c55e" if report.pass_rate >= 90 else ("#ef4444" if report.pass_rate < 80 else "#f59e0b")

    # Build result rows
    results_html = ""
    results = report.raw_data.get("results", []) if report.raw_data else []
    for r in results:
        icon = "PASS" if r.get("passed") else "FAIL"
        c = "#22c55e" if r.get("passed") else "#ef4444"
        msgs = "<br>".join(r.get("messages", []))
        results_html += f"""
        <tr>
            <td style="color:{c};font-weight:bold">{icon}</td>
            <td>{r.get("method", "")}</td>
            <td>{r.get("path", "")}</td>
            <td>{r.get("status_code", "-")}</td>
            <td>{r.get("response_time_ms", "-")}ms</td>
            <td style="font-size:12px">{msgs}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Report #{report.id} - Test Report Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
nav {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px 40px; display:flex; justify-content:space-between; align-items:center; }}
nav h1 {{ font-size: 20px; }}
nav a {{ color: white; text-decoration: none; opacity: 0.9; }}
nav a:hover {{ opacity: 1; }}
.container {{ max-width: 1000px; margin: 30px auto; padding: 0 20px; }}
.stats {{ display: flex; gap: 15px; margin-bottom: 20px; }}
.stat {{ flex:1; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
.stat .num {{ font-size: 28px; font-weight: bold; }}
.stat .label {{ color: #888; font-size: 13px; margin-top: 4px; }}
.card {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 24px; margin-bottom: 20px; }}
.card h2 {{ margin-bottom: 16px; font-size: 18px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 12px 16px; border-bottom: 1px solid #f1f5f9; }}
th {{ font-size: 12px; text-transform: uppercase; color: #888; }}
td {{ font-size: 14px; }}
</style>
</head>
<body>
<nav>
    <h1><a href="/">Test Report Dashboard</a> / <a href="/projects/{project.id}">{project.name}</a> / Report #{report.id}</h1>
</nav>
<div class="container">
    <div class="stats">
        <div class="stat"><div class="num">{report.total}</div><div class="label">Total Tests</div></div>
        <div class="stat"><div class="num" style="color:#22c55e">{report.passed}</div><div class="label">Passed</div></div>
        <div class="stat"><div class="num" style="color:#ef4444">{report.failed}</div><div class="label">Failed</div></div>
        <div class="stat"><div class="num" style="color:{color}">{report.pass_rate}%</div><div class="label">Pass Rate</div></div>
    </div>
    <div class="card">
        <h2>Test Results</h2>
        <table>
        <thead><tr><th>Status</th><th>Method</th><th>Path</th><th>Code</th><th>Time</th><th>Details</th></tr></thead>
        <tbody>{results_html}</tbody>
        </table>
    </div>
</div>
</body>
</html>"""
    return html