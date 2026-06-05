from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import json, os

from .database import engine, get_db, Base
from .models import Project, Report
from .schemas import ProjectOut, ReportOut, ReportDetail

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Test Report Dashboard")

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ─── Helpers ────────────────────────────────────────────────────────

def process_upload(data: dict, db: Session):
    project_name = data.get("project_name", "Unnamed")
    summary = data.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0
    total_time_ms = data.get("total_time_ms", 0)

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
    return report, project_name, pass_rate


# ─── API Routes ───────────────────────────────────────────────────

@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    result = []
    for p in projects:
        latest = db.query(Report).filter(Report.project_id == p.id).order_by(desc(Report.uploaded_at)).first()
        count = db.query(Report).filter(Report.project_id == p.id).count()
        result.append(ProjectOut(
            id=p.id, name=p.name, description=p.description or "",
            report_count=count,
            latest_pass_rate=latest.pass_rate if latest else None,
            latest_at=latest.uploaded_at if latest else None,
        ))
    return result


@app.get("/api/projects/{project_id}/reports")
def list_reports(project_id: int, db: Session = Depends(get_db)):
    return db.query(Report).filter(Report.project_id == project_id).order_by(desc(Report.uploaded_at)).all()


@app.get("/api/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return {"error": "Not found"}
    return ReportDetail(
        id=report.id, project_id=report.project_id,
        total=report.total, passed=report.passed, failed=report.failed,
        pass_rate=report.pass_rate, total_time_ms=report.total_time_ms or 0,
        uploaded_at=report.uploaded_at, raw_data=report.raw_data,
    )


@app.post("/api/upload")
async def upload_report(file: UploadFile = File(None), db: Session = Depends(get_db)):
    """Upload via file."""
    if not file:
        return {"error": "No file provided"}
    content = await file.read()
    data = json.loads(content)
    report, name, rate = process_upload(data, db)
    return {"id": report.id, "project": name, "pass_rate": rate}


@app.post("/api/upload-text")
async def upload_text(request: Request, db: Session = Depends(get_db)):
    """Upload via JSON text."""
    body = await request.json()
    report, name, rate = process_upload(body, db)
    return {"id": report.id, "project": name, "pass_rate": rate}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "Not found"}
    db.delete(project)
    db.commit()
    return {"deleted": project_id}


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return {"error": "Not found"}
    pid = report.project_id
    db.delete(report)
    db.commit()
    count = db.query(Report).filter(Report.project_id == pid).count()
    if count == 0:
        db.query(Project).filter(Project.id == pid).delete()
        db.commit()
    return {"deleted": report_id}


@app.get("/api/projects/{project_id}/stats")
def project_stats(project_id: int, db: Session = Depends(get_db)):
    """Get trend data for a project."""
    reports = db.query(Report).filter(Report.project_id == project_id).order_by(Report.uploaded_at).all()
    return {
        "labels": [r.uploaded_at.strftime("%m-%d %H:%M") for r in reports],
        "pass_rates": [r.pass_rate for r in reports],
        "avg_times": [round(r.total_time_ms / r.total, 1) if r.total > 0 else 0 for r in reports],
        "totals": [r.total for r in reports],
        "passed": [r.passed for r in reports],
        "failed": [r.failed for r in reports],
    }


# ─── Frontend Pages ───────────────────────────────────────────────

PAGE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Test Report Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f7fa;color:#333}
nav{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:20px 40px;display:flex;justify-content:space-between;align-items:center}
nav h1{font-size:20px}
nav a{color:white;text-decoration:none;opacity:.9;margin-left:16px}
nav a:hover{opacity:1}
.container{max-width:1000px;margin:30px auto;padding:0 20px}
.card{background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);padding:24px;margin-bottom:20px}
.card h2{margin-bottom:16px;font-size:18px}
.stats{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}
.stat{flex:1;min-width:120px;background:white;padding:20px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);text-align:center}
.stat .num{font-size:28px;font-weight:bold}
.stat .label{color:#888;font-size:13px;margin-top:4px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:12px 16px;border-bottom:1px solid #f1f5f9}
th{font-size:12px;text-transform:uppercase;color:#888}
td{font-size:14px}
td a{color:#667eea;text-decoration:none}
td a:hover{text-decoration:underline}
button,.btn{background:#667eea;color:white;border:none;padding:10px 24px;border-radius:6px;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block}
button:hover,.btn:hover{background:#5a6fd6}
.btn-danger{background:#ef4444}
.btn-danger:hover{background:#dc2626}
.btn-sm{padding:5px 12px;font-size:12px}
form{display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap}
textarea,input[type="file"]{padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px}
textarea{width:100%;min-height:120px;font-family:monospace;font-size:12px}
.tabs{display:flex;gap:0;margin-bottom:20px}
.tab{padding:8px 20px;background:#e5e7eb;border-radius:8px 8px 0 0;cursor:pointer;font-size:14px}
.tab.active{background:#667eea;color:white}
canvas{max-width:100%}
#status{margin-top:10px;font-size:14px;padding:8px 16px;border-radius:6px}
#status.success{background:#dcfce7;color:#16a34a}
#status.error{background:#fee2e2;color:#dc2626}
</style>
</head>
<body>
<nav>
    <h1><a href="/">Test Report Dashboard</a></h1>
    <div><a href="/api/projects">API</a></div>
</nav>
<div class="container">
"""

PAGE_FOOT = """</div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    rows = ""
    for p in projects:
        count = db.query(Report).filter(Report.project_id == p.id).count()
        latest = db.query(Report).filter(Report.project_id == p.id).order_by(desc(Report.uploaded_at)).first()
        rate = f"{latest.pass_rate:.0f}%" if latest else "-"
        color = "#22c55e" if latest and latest.pass_rate >= 90 else ("#ef4444" if latest and latest.pass_rate < 80 else "#f59e0b")
        date_str = latest.uploaded_at.strftime("%Y-%m-%d %H:%M") if latest else "-"
        rows += f"""<tr>
            <td><a href="/projects/{p.id}">{p.name}</a></td>
            <td>{p.description or ""}</td>
            <td>{count}</td>
            <td><span style="color:{color};font-weight:bold">{rate}</span></td>
            <td>{date_str}</td>
            <td><button class="btn-danger btn-sm" onclick="delProject({p.id})">Delete</button></td>
        </tr>"""

    html = PAGE_HEAD + """
<div class="tabs">
    <div class="tab active" onclick="showTab('file')">File Upload</div>
    <div class="tab" onclick="showTab('text')">Paste JSON</div>
</div>
<div class="card" id="tab-file">
    <h2>Upload Report File</h2>
    <form id="uploadForm" enctype="multipart/form-data">
        <input type="file" id="file" name="file" accept=".json">
        <button type="submit">Upload</button>
    </form>
    <div id="status"></div>
</div>
<div class="card" id="tab-text" style="display:none">
    <h2>Paste JSON Report</h2>
    <form id="textForm">
        <textarea id="jsonText" placeholder='{"project_name": "My API", "summary": {"total": 10, "passed": 9, "failed": 1}, "results": [...]}'></textarea>
        <button type="submit">Submit</button>
    </form>
    <div id="status2"></div>
</div>
<div class="card">
    <h2>Projects</h2>
    <table>
    <thead><tr><th>Project</th><th>Description</th><th>Reports</th><th>Latest Rate</th><th>Last Run</th><th></th></tr></thead>
    <tbody>""" + rows + """</tbody>
    </table>
</div>
<script>
function showTab(name) {
    document.getElementById('tab-file').style.display = name==='file'?'block':'none';
    document.getElementById('tab-text').style.display = name==='text'?'block':'none';
    document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',(i===0&&name==='file')||(i===1&&name==='text')));
}
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData();
    fd.append('file', document.getElementById('file').files[0]);
    const r = await fetch('/api/upload', {method:'POST',body:fd});
    const d = await r.json();
    const s = document.getElementById('status');
    if(d.error) { s.className='error'; s.textContent=d.error; }
    else { s.className='success'; s.textContent='Uploaded! Pass rate: '+d.pass_rate+'%'; setTimeout(()=>location.reload(),1000); }
});
document.getElementById('textForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
        const data = JSON.parse(document.getElementById('jsonText').value);
        const r = await fetch('/api/upload-text', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
        const d = await r.json();
        const s = document.getElementById('status2');
        if(d.error) { s.className='error'; s.textContent=d.error; }
        else { s.className='success'; s.textContent='Uploaded! Pass rate: '+d.pass_rate+'%'; setTimeout(()=>location.reload(),1000); }
    } catch(err) { document.getElementById('status2').className='error'; document.getElementById('status2').textContent='Invalid JSON'; }
});
async function delProject(id) {
    if(!confirm('Delete this project and all its reports?')) return;
    await fetch('/api/projects/'+id, {method:'DELETE'});
    location.reload();
}
</script>
""" + PAGE_FOOT
    return html


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return HTMLResponse("<h2>Not Found</h2>", status_code=404)

    reports = db.query(Report).filter(Report.project_id == project_id).order_by(Report.uploaded_at).all()

    rows = ""
    for r in reversed(reports):
        color = "#22c55e" if r.pass_rate >= 90 else ("#ef4444" if r.pass_rate < 80 else "#f59e0b")
        rows += f"""<tr>
            <td><a href="/reports/{r.id}">{r.uploaded_at.strftime("%Y-%m-%d %H:%M")}</a></td>
            <td>{r.total}</td>
            <td style="color:#22c55e">{r.passed}</td>
            <td style="color:#ef4444">{r.failed}</td>
            <td><span style="color:{color};font-weight:bold">{r.pass_rate:.0f}%</span></td>
            <td>{r.total_time_ms:.0f}ms</td>
            <td><button class="btn-danger btn-sm" onclick="delReport({r.id})">Del</button></td>
        </tr>"""

    latest_rate = reports[-1].pass_rate if reports else 0
    avg_time = round(sum(r.total_time_ms for r in reports) / len(reports), 1) if reports else 0

    html = PAGE_HEAD + f"""
<nav style="margin:-30px -20px 20px">
    <h1><a href="/">Dashboard</a> / {project.name}</h1>
</nav>
<div class="stats">
    <div class="stat"><div class="num" style="color:#667eea">{len(reports)}</div><div class="label">Reports</div></div>
    <div class="stat"><div class="num" style="color:#22c55e">{latest_rate:.0f}%</div><div class="label">Latest Rate</div></div>
    <div class="stat"><div class="num" style="color:#f59e0b">{avg_time}ms</div><div class="label">Avg Time</div></div>
</div>
<div class="card">
    <h2>Pass Rate Trend</h2>
    <canvas id="rateChart"></canvas>
</div>
<div class="card">
    <h2>Response Time Trend</h2>
    <canvas id="timeChart"></canvas>
</div>
<div class="card">
    <h2>Reports</h2>
    <table>
    <thead><tr><th>Date</th><th>Total</th><th>Passed</th><th>Failed</th><th>Rate</th><th>Time</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
    </table>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
async function loadCharts() {{
    const r = await fetch('/api/projects/{project_id}/stats');
    const d = await r.json();
    const opts = (label,color) => ({{
        type:'line', data:{{labels:d.labels,datasets:[{{label,data:d[label],borderColor:color,backgroundColor:color+'20',fill:true,tension:.3}}]}},
        options:{{scales:{{y:{{min:label==='pass_rates'?0:undefined,max:label==='pass_rates'?100:undefined}}}}}}
    }});
    new Chart(document.getElementById('rateChart'), opts('pass_rates','#667eea'));
    new Chart(document.getElementById('timeChart'), opts('avg_times','#f59e0b'));
}}
loadCharts();
async function delReport(id) {{ if(!confirm('Delete this report?')) return; await fetch('/api/reports/'+id,{{method:'DELETE'}}); location.reload(); }}
</script>
""" + PAGE_FOOT
    return html


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return HTMLResponse("<h2>Not Found</h2>", status_code=404)

    project = db.query(Project).filter(Project.id == report.project_id).first()
    color = "#22c55e" if report.pass_rate >= 90 else ("#ef4444" if report.pass_rate < 80 else "#f59e0b")

    results_html = ""
    results = report.raw_data.get("results", []) if report.raw_data else []
    for r in results:
        icon = "PASS" if r.get("passed") else "FAIL"
        c = "#22c55e" if r.get("passed") else "#ef4444"
        msgs = "<br>".join(r.get("messages", []))
        results_html += f"""<tr>
            <td style="color:{c};font-weight:bold">{icon}</td>
            <td>{r.get("method", "")}</td>
            <td>{r.get("path", "")}</td>
            <td>{r.get("status_code", "-")}</td>
            <td>{r.get("response_time_ms", "-")}ms</td>
            <td style="font-size:12px">{msgs}</td>
        </tr>"""

    html = PAGE_HEAD + f"""
<nav style="margin:-30px -20px 20px">
    <h1><a href="/">Dashboard</a> / <a href="/projects/{project.id}">{project.name}</a> / Report #{report.id}</h1>
</nav>
<div class="stats">
    <div class="stat"><div class="num">{report.total}</div><div class="label">Total Tests</div></div>
    <div class="stat"><div class="num" style="color:#22c55e">{report.passed}</div><div class="label">Passed</div></div>
    <div class="stat"><div class="num" style="color:#ef4444">{report.failed}</div><div class="label">Failed</div></div>
    <div class="stat"><div class="num" style="color:{color}">{report.pass_rate:.0f}%</div><div class="label">Pass Rate</div></div>
</div>
<div class="card">
    <h2>Test Results</h2>
    <table>
    <thead><tr><th>Status</th><th>Method</th><th>Path</th><th>Code</th><th>Time</th><th>Details</th></tr></thead>
    <tbody>{results_html}</tbody>
    </table>
</div>
""" + PAGE_FOOT
    return html