from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import csv, io, json, os

from .database import engine, get_db, Base
from .models import Project, Report
from .schemas import ProjectOut, ReportOut, ReportDetail

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Test Report Dashboard")

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

PAGE_SIZE = 20


# ---- Helpers ----

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


# ---- API Routes ----

@app.get("/api/projects")
def list_projects(search: str = Query(default=""), db: Session = Depends(get_db)):
    query = db.query(Project)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))
    projects = query.all()
    result = []
    for p in projects:
        latest = db.query(Report).filter(
            Report.project_id == p.id
        ).order_by(desc(Report.uploaded_at)).first()
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
    return db.query(Report).filter(
        Report.project_id == project_id
    ).order_by(desc(Report.uploaded_at)).all()


@app.get("/api/projects/{project_id}/stats")
def project_stats(project_id: int, db: Session = Depends(get_db)):
    reports = db.query(Report).filter(
        Report.project_id == project_id
    ).order_by(Report.uploaded_at).all()
    return {
        "labels": [r.uploaded_at.strftime("%m-%d %H:%M") for r in reports],
        "pass_rates": [r.pass_rate for r in reports],
        "avg_times": [r.total_time_ms for r in reports],
    }


@app.get("/api/projects/{project_id}/export")
def export_reports(project_id: int, fmt: str = Query(default="json"), db: Session = Depends(get_db)):
    reports = db.query(Report).filter(
        Report.project_id == project_id
    ).order_by(Report.uploaded_at).all()
    project = db.query(Project).filter(Project.id == project_id).first()
    name = project.name if project else "unknown"

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Total", "Passed", "Failed", "Pass Rate", "Time (ms)"])
        for r in reports:
            writer.writerow([
                r.uploaded_at.isoformat(), r.total, r.passed, r.failed,
                r.pass_rate, r.total_time_ms,
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={name}_reports.csv"},
        )
    else:
        data = {
            "project": name,
            "reports": [
                {
                    "date": r.uploaded_at.isoformat(),
                    "total": r.total,
                    "passed": r.passed,
                    "failed": r.failed,
                    "pass_rate": r.pass_rate,
                    "total_time_ms": r.total_time_ms,
                    "results": r.raw_data.get("results", []) if r.raw_data else [],
                }
                for r in reports
            ],
        }
        return data


@app.get("/api/compare/{report_id_a}/{report_id_b}")
def compare_reports(report_id_a: int, report_id_b: int, db: Session = Depends(get_db)):
    ra = db.query(Report).filter(Report.id == report_id_a).first()
    rb = db.query(Report).filter(Report.id == report_id_b).first()
    if not ra or not rb:
        return {"error": "One or both reports not found"}
    return {
        "a": {"id": ra.id, "date": ra.uploaded_at.isoformat(), "total": ra.total,
              "passed": ra.passed, "failed": ra.failed, "pass_rate": ra.pass_rate},
        "b": {"id": rb.id, "date": rb.uploaded_at.isoformat(), "total": rb.total,
              "passed": rb.passed, "failed": rb.failed, "pass_rate": rb.pass_rate},
        "delta": {
            "pass_rate": round(rb.pass_rate - ra.pass_rate, 1),
            "total_time_ms": round((rb.total_time_ms or 0) - (ra.total_time_ms or 0), 1),
            "passed": rb.passed - ra.passed,
            "failed": rb.failed - ra.failed,
        },
    }


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
    if not file:
        return {"error": "No file provided"}
    content = await file.read()
    data = json.loads(content)
    report, name, rate = process_upload(data, db)
    return {"id": report.id, "project": name, "pass_rate": rate}


@app.post("/api/upload-text")
async def upload_text(request: Request, db: Session = Depends(get_db)):
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
    db.delete(report)
    db.commit()
    return {"deleted": report_id}


# ---- HTML Pages ----

PAGE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Test Report Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333}
.container{max-width:1100px;margin:0 auto;padding:30px 20px}
nav{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;padding:20px 30px;border-radius:12px;margin-bottom:20px}
nav h1{font-size:22px}nav a{color:#fff;text-decoration:none}nav a:hover{text-decoration:underline}
.stats{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap}
.stat{flex:1;min-width:140px;background:#fff;padding:20px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.08);text-align:center}
.stat .num{font-size:28px;font-weight:bold}.stat .label{font-size:13px;color:#888;margin-top:4px}
.card{background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.08);padding:20px;margin-bottom:20px}
.card h2{font-size:16px;margin-bottom:15px;color:#555}
table{width:100%;border-collapse:collapse}
th{background:#f8fafc;text-align:left;padding:10px 14px;font-size:12px;text-transform:uppercase;color:#888}
td{padding:10px 14px;border-top:1px solid #f1f5f9;font-size:14px}
.btn{padding:8px 18px;border:none;border-radius:6px;cursor:pointer;font-size:14px}
.btn-primary{background:#667eea;color:#fff}
.btn-danger{background:#ef4444;color:#fff;padding:6px 12px;font-size:12px}
.btn-sm{padding:5px 10px;font-size:12px}
.btn-success{background:#22c55e;color:#fff;padding:6px 12px;font-size:12px}
.btn-outline{padding:6px 12px;font-size:12px;border:1px solid #ddd;background:#fff;border-radius:6px;cursor:pointer}
.search-box{padding:8px 14px;border:1px solid #ddd;border-radius:6px;font-size:14px;width:250px}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:15px;flex-wrap:wrap}
.pagination{display:flex;gap:8px;justify-content:center;margin-top:15px}
.pagination button{padding:6px 14px;border:1px solid #ddd;background:#fff;border-radius:6px;cursor:pointer}
.pagination button.active{background:#667eea;color:#fff;border-color:#667eea}
.empty-state{text-align:center;padding:60px 20px;color:#888}
.empty-state h2{font-size:20px;margin-bottom:10px;color:#666}
.empty-state p{font-size:14px;margin-bottom:20px}
input[type=file]{font-size:14px}
.compare-grid{display:grid;grid-template-columns:1fr auto 1fr;gap:20px;align-items:center}
.compare-card{text-align:center;padding:15px;background:#f8fafc;border-radius:8px}
.compare-delta{font-size:14px;font-weight:bold}
.compare-delta.up{color:#22c55e}.compare-delta.down{color:#ef4444}
</style>
</head>
<body><div class="container">
"""

PAGE_FOOT = """</div></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = Query(default=""), db: Session = Depends(get_db)):
    query = db.query(Project)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))
    projects = query.order_by(Project.created_at.desc()).all()

    total_reports = db.query(Report).count()
    avg_rate = db.query(func.avg(Report.pass_rate)).scalar() or 0

    rows = ""
    if projects:
        for p in projects:
            latest = db.query(Report).filter(
                Report.project_id == p.id
            ).order_by(desc(Report.uploaded_at)).first()
            count = db.query(Report).filter(Report.project_id == p.id).count()
            rate = latest.pass_rate if latest else None
            date_str = latest.uploaded_at.strftime("%Y-%m-%d %H:%M") if latest and latest.uploaded_at else "-"
            color = "#22c55e" if rate and rate >= 90 else ("#ef4444" if rate and rate < 80 else "#f59e0b")
            rate_display = f"{rate:.0f}%" if rate is not None else "-"
            rows += f"""<tr>
                <td><a href="/projects/{p.id}" style="color:#667eea;font-weight:bold;text-decoration:none">{p.name}</a></td>
                <td>{count}</td>
                <td style="color:{color};font-weight:bold">{rate_display}</td>"""
            rows += f"""
                <td style="font-size:13px;color:#888">{date_str}</td>
                <td>
                    <button class="btn-outline" onclick="location.href='/projects/{p.id}'">View</button>
                    <button class="btn-danger btn-sm" onclick="delProject({p.id})">Del</button>
                </td>
            </tr>"""
    else:
        rows = """<tr><td colspan="5" style="text-align:center;padding:40px;color:#888">
            No projects yet. Upload a JSON report to get started.</td></tr>"""

    html = PAGE_HEAD + f"""
<nav style="margin:-30px -20px 20px">
    <h1>Test Report Dashboard</h1>
</nav>
<div class="stats">
    <div class="stat"><div class="num" style="color:#667eea">{len(projects)}</div><div class="label">Projects</div></div>
    <div class="stat"><div class="num" style="color:#22c55e">{total_reports}</div><div class="label">Total Reports</div></div>
    <div class="stat"><div class="num" style="color:#f59e0b">{avg_rate:.0f}%</div><div class="label">Avg Pass Rate</div></div>
</div>
<div class="card">
    <div class="toolbar">
        <h2>Projects</h2>
        <input type="text" class="search-box" placeholder="Search projects..." value="{search}"
               oninput="location.search='?search='+encodeURIComponent(this.value)">
        <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()">+ Upload JSON</button>
        <form id="uploadForm" action="/api/upload" method="post" enctype="multipart/form-data" style="display:none">
            <input id="fileInput" type="file" name="file" accept=".json" onchange="uploadFile(this)">
        </form>
        <div id="pasteArea" style="display:none;margin-top:10px;width:100%">
            <textarea id="pasteText" placeholder='Paste JSON report data...' style="width:100%;height:100px;padding:8px;border:1px solid #ddd;border-radius:6px;font-family:monospace;font-size:13px"></textarea>
            <button class="btn btn-success" onclick="pasteUpload()" style="margin-top:5px">Submit Pasted JSON</button>
            <button class="btn-outline" onclick="document.getElementById('pasteArea').style.display='none'" style="margin-top:5px">Cancel</button>
        </div>
        <button class="btn-outline" onclick="document.getElementById('pasteArea').style.display='block'" style="margin-left:5px">Paste JSON</button>
    </div>
    <table>
    <thead><tr><th>Project</th><th>Reports</th><th>Latest Rate</th><th>Last Run</th><th>Actions</th></tr></thead>
    <tbody>{rows}</tbody>
    </table>
</div>
<script>
async function uploadFile(input) {{
    if(!input.files[0]) return;
    const fd = new FormData();
    fd.append('file', input.files[0]);
    await fetch('/api/upload', {{method:'POST',body:fd}});
    location.reload();
}}
async function pasteUpload() {{
    const text = document.getElementById('pasteText').value;
    if(!text) return;
    await fetch('/api/upload-text', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:text}});
    location.reload();
}}
async function delProject(id) {{
    if(!confirm('Delete this project and all its reports?')) return;
    await fetch('/api/projects/'+id, {{method:'DELETE'}});
    location.reload();
}}
</script>
""" + PAGE_FOOT
    return html


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: int, request: Request,
                         page: int = Query(default=1, ge=1),
                         db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return HTMLResponse("<h2>Not Found</h2>", status_code=404)

    all_reports = db.query(Report).filter(
        Report.project_id == project_id
    ).order_by(desc(Report.uploaded_at)).all()

    total_pages = max(1, (len(all_reports) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    start = (page - 1) * PAGE_SIZE
    page_reports = all_reports[start:start + PAGE_SIZE]

    rows = ""
    for r in page_reports:
        color = "#22c55e" if r.pass_rate >= 90 else ("#ef4444" if r.pass_rate < 80 else "#f59e0b")
        rows += f"""<tr>
            <td><a href="/reports/{r.id}" style="color:#667eea">{r.uploaded_at.strftime("%Y-%m-%d %H:%M")}</a></td>
            <td>{r.total}</td>
            <td style="color:#22c55e">{r.passed}</td>
            <td style="color:#ef4444">{r.failed}</td>
            <td><span style="color:{color};font-weight:bold">{r.pass_rate:.0f}%</span></td>
            <td>{r.total_time_ms:.0f}ms</td>
            <td>
                <button class="btn-sm" style="background:#667eea;color:#fff;border:none;border-radius:4px;cursor:pointer;margin-right:4px"
                        onclick="selectCompare({r.id})">Compare</button>
                <button class="btn-danger btn-sm" onclick="delReport({r.id})">Del</button>
            </td>
        </tr>"""

    # Pagination buttons
    pagination = ""
    if total_pages > 1:
        for i in range(1, total_pages + 1):
            cls = "active" if i == page else ""
            pagination += f'<button class="{cls}" onclick="location.href=\'?page={i}\'">{i}</button>'

    latest_rate = all_reports[0].pass_rate if all_reports else 0
    avg_time = round(sum(r.total_time_ms for r in all_reports) / len(all_reports), 1) if all_reports else 0

    html = PAGE_HEAD + f"""
<nav style="margin:-30px -20px 20px">
    <h1><a href="/">Dashboard</a> / {project.name}</h1>
</nav>
<div class="stats">
    <div class="stat"><div class="num" style="color:#667eea">{len(all_reports)}</div><div class="label">Reports</div></div>
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
    <div class="toolbar">
        <h2>Reports</h2>
        <a href="/api/projects/{project_id}/export?fmt=csv" class="btn-outline" style="text-decoration:none">Export CSV</a>
        <a href="/api/projects/{project_id}/export?fmt=json" class="btn-outline" style="text-decoration:none">Export JSON</a>
        <span id="compareInfo" style="font-size:13px;color:#888;margin-left:10px"></span>
    </div>
    <table>
    <thead><tr><th>Date</th><th>Total</th><th>Passed</th><th>Failed</th><th>Rate</th><th>Time</th><th>Actions</th></tr></thead>
    <tbody>{rows}</tbody>
    </table>
    <div class="pagination">{pagination}</div>
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
let compareA = null;
function selectCompare(id) {{
    if(!compareA) {{ compareA = id; document.getElementById('compareInfo').textContent = 'Selected #'+id+'. Now click Compare on another report.'; }}
    else if(compareA === id) {{ compareA = null; document.getElementById('compareInfo').textContent = ''; }}
    else {{ location.href = '/compare/'+compareA+'/'+id; compareA = null; }}
}}
async function delReport(id) {{ if(!confirm('Delete this report?')) return; await fetch('/api/reports/'+id,{{method:'DELETE'}}); location.reload(); }}
</script>
""" + PAGE_FOOT
    return html


@app.get("/compare/{report_id_a}/{report_id_b}", response_class=HTMLResponse)
async def compare_page(report_id_a: int, report_id_b: int, db: Session = Depends(get_db)):
    ra = db.query(Report).filter(Report.id == report_id_a).first()
    rb = db.query(Report).filter(Report.id == report_id_b).first()
    if not ra or not rb:
        return HTMLResponse("<h2>Reports not found</h2>", status_code=404)

    pa = db.query(Project).filter(Project.id == ra.project_id).first()
    pb = db.query(Project).filter(Project.id == rb.project_id).first()

    def color_class(val):
        return "up" if val > 0 else "down" if val < 0 else ""

    delta_pass = round(rb.pass_rate - ra.pass_rate, 1)
    delta_time = round((rb.total_time_ms or 0) - (ra.total_time_ms or 0), 1)

    html = PAGE_HEAD + f"""
<nav style="margin:-30px -20px 20px">
    <h1><a href="/">Dashboard</a> / Compare Reports</h1>
</nav>
<div class="compare-grid">
    <div class="compare-card">
        <h3>Report A</h3>
        <p style="color:#888;font-size:13px">{ra.uploaded_at.strftime("%Y-%m-%d %H:%M")}</p>
        <p>Project: {pa.name if pa else '?'}</p>
        <div class="stat"><div class="num">{ra.total}</div><div class="label">Total</div></div>
        <div class="stat"><div class="num" style="color:#22c55e">{ra.passed}</div><div class="label">Passed</div></div>
        <div class="stat"><div class="num" style="color:#ef4444">{ra.failed}</div><div class="label">Failed</div></div>
        <div class="stat"><div class="num">{ra.pass_rate:.0f}%</div><div class="label">Pass Rate</div></div>
        <div class="stat"><div class="num">{ra.total_time_ms:.0f}ms</div><div class="label">Time</div></div>
    </div>
    <div style="text-align:center;font-size:24px;color:#888">vs</div>
    <div class="compare-card">
        <h3>Report B</h3>
        <p style="color:#888;font-size:13px">{rb.uploaded_at.strftime("%Y-%m-%d %H:%M")}</p>
        <p>Project: {pb.name if pb else '?'}</p>
        <div class="stat"><div class="num">{rb.total}</div><div class="label">Total</div></div>
        <div class="stat"><div class="num" style="color:#22c55e">{rb.passed}</div><div class="label">Passed</div></div>
        <div class="stat"><div class="num" style="color:#ef4444">{rb.failed}</div><div class="label">Failed</div></div>
        <div class="stat"><div class="num">{rb.pass_rate:.0f}%</div><div class="label">Pass Rate</div></div>
        <div class="stat"><div class="num">{rb.total_time_ms:.0f}ms</div><div class="label">Time</div></div>
    </div>
</div>
<div class="card" style="margin-top:20px">
    <h2>Delta (B - A)</h2>
    <div class="stats">
        <div class="stat"><div class="num">{rb.total - ra.total}</div><div class="label">Total Diff</div></div>
        <div class="stat"><div class="num" style="color:{'#22c55e' if delta_pass > 0 else '#ef4444' if delta_pass < 0 else '#888'}">{delta_pass:+.1f}%</div><div class="label">Pass Rate</div></div>
        <div class="stat"><div class="num" style="color:{'#ef4444' if delta_time > 0 else '#22c55e' if delta_time < 0 else '#888'}">{delta_time:+.0f}ms</div><div class="label">Response Time</div></div>
    </div>
</div>
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