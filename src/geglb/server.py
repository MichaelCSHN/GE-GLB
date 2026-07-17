"""GE-GLB local web dashboard — FastAPI backend.

Start with ``geglb serve``.  The dashboard is read-only: it scans a build
directory and exposes project metadata, trajectory maps, and product
previews through a browser.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ── scan state ─────────────────────────────────────────────────────────
_scan_root: Path | None = None
_project_cache: dict[str, dict[str, object]] = {}


def _scan_projects(root: Path) -> dict[str, dict[str, object]]:
    """Scan *root* for build sub-directories containing a manifest."""
    projects: dict[str, dict[str, object]] = {}
    if not root.is_dir():
        return projects
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / "manifest.json"
        if not manifest.is_file():
            continue
        name = child.name
        info = _read_project_info(child)
        if info:
            projects[name] = info
    return projects


def _read_project_info(project_dir: Path) -> dict[str, object] | None:
    """Extract summary metadata from a single project directory."""
    try:
        manifest = json.loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    source = manifest.get("source", {})
    source_kind = source.get("kind", "unknown")
    status = manifest.get("status", "unknown")
    counts = manifest.get("counts", {})

    products: dict[str, dict[str, object]] = {}
    product_dir = project_dir / "product"
    for task, pname in [
        ("underbody", "underbody.png"),
        ("panorama", "panorama.png"),
        ("lookat", "viewset.json"),
    ]:
        prod_manifest = product_dir / "manifest.json"
        has_product = prod_manifest.is_file()
        artifact = product_dir / pname
        diag = product_dir / "diagnostics"
        products[task] = {
            "exists": has_product and artifact.is_file(),
            "has_diagnostics": diag.is_dir(),
            "image": f"/static/{project_dir.name}/product/{pname}",
        }

    return {
        "name": project_dir.name,
        "has_manifest": True,
        "has_trajectory": (project_dir / "trajectory.jsonl").is_file(),
        "has_capture": (project_dir / "frames.jsonl").is_file(),
        "has_product": {t: p["exists"] for t, p in products.items()},
        "source_kind": source_kind,
        "status": status,
        "trajectory_points": counts.get("trajectory_frames", 0),
        "image_frames": counts.get("image_frames", 0),
        "products": products,
    }


def _get_project(name: str) -> dict[str, object] | None:
    """Return cached project info, re-reading from disk."""
    if _scan_root is None:
        return None
    project_dir = _scan_root / name
    if not project_dir.is_dir():
        return None
    return _read_project_info(project_dir)


# ── FastAPI app ────────────────────────────────────────────────────────

app = FastAPI(title="GE-GLB Dashboard")


@app.on_event("startup")
def _on_startup() -> None:
    """Initial scan on startup (no-op — scan happens in serve command)."""


# ── API routes ─────────────────────────────────────────────────────────


@app.get("/api/projects")
async def api_projects() -> dict[str, object]:
    global _project_cache
    if _scan_root is not None:
        _project_cache = _scan_projects(_scan_root)
    return {"projects": list(_project_cache.values())}


@app.get("/api/project/{name}")
async def api_project(name: str):
    info = _get_project(name)
    if info is None:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": f"project {name!r} not found"}, status_code=404)
    return info


@app.get("/api/project/{name}/trajectory")
async def api_trajectory(name: str):
    if _scan_root is None:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "scan root not set"}, status_code=500)
    project_dir = _scan_root / name
    traj_path = project_dir / "trajectory.jsonl"
    if not traj_path.is_file():
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": "trajectory data not found"}, status_code=404)
    points = []
    for line in traj_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            points.append(json.loads(line))
    return {"trajectory": points}


@app.get("/api/project/{name}/product/{task}")
async def api_product(name: str, task: str):
    info = _get_project(name)
    if info is None:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": f"project {name!r} not found"}, status_code=404)
    products = info.get("products", {})
    product_info = products.get(task)
    if product_info is None:
        from fastapi.responses import JSONResponse

        return JSONResponse({"error": f"task {task!r} not supported"}, status_code=404)
    return dict(product_info)


# ── inline HTML templates ──────────────────────────────────────────────

_STYLE = """<style>
body{font-family:system-ui,sans-serif;margin:2rem;background:#f5f5f5}
.card{background:#fff;padding:1.5rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.1)}
table{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}
th,td{padding:.75rem 1rem;text-align:left;border-bottom:1px solid #eee}
th{background:#f9f9f9}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
.dot-ok{background:#4caf50}.dot-no{background:#f44336}
a{color:#1976d2;text-decoration:none}
.gallery{display:flex;gap:1rem;flex-wrap:wrap}
.gallery img{max-width:400px;max-height:300px}
</style>"""


def _project_list_html(projects: list[dict]) -> str:
    rows = []
    for p in projects:
        products = p.get("has_product", {})
        row = (
            f"<tr>"
            f"<td><a href='/project/{p['name']}'>{p['name']}</a></td>"
            f"<td>{p['source_kind']}</td>"
            f"<td>{p['status']}</td>"
            f"<td><span class='dot "
            f"{'dot-ok' if products.get('underbody') else 'dot-no'}'></span></td>"
            f"<td><span class='dot "
            f"{'dot-ok' if products.get('panorama') else 'dot-no'}'></span></td>"
            f"<td><span class='dot "
            f"{'dot-ok' if products.get('lookat') else 'dot-no'}'></span></td>"
            f"<td>{p['image_frames']}</td>"
            f"</tr>"
        )
        rows.append(row)
    body = (
        "<p>No projects found.</p>"
        if not rows
        else f"<table><thead><tr>"
        f"<th>Project</th><th>Source</th><th>Status</th>"
        f"<th>Underbody</th><th>Panorama</th><th>LookAt</th>"
        f"<th>Frames</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    return "<!DOCTYPE html><html><head><meta charset=utf-8>"
    f"<title>GE-GLB Dashboard</title>{_STYLE}</head>"
    f"<body><h1>GE-GLB Dashboard</h1>{body}</body></html>"


def _project_detail_html(project: dict) -> str:
    products_html = ""
    for task, info in project.get("products", {}).items():
        if not info["exists"]:
            continue
        if task == "panorama":
            img = f"<a href='/project/{project['name']}/pano'>Open Panorama Viewer</a>"
        else:
            img = f"<img src='{info['image']}' alt='{task}'>"
        products_html += f"<div class=gallery-item><h3>{task}</h3>{img}</div>"

    traj_section = ""
    if project.get("has_trajectory"):
        traj_section = (
            f"<div class=card><h2>Route Map</h2>"
            f"<iframe src='/maps/{project['name']}.html' "
            f"width='100%' height='400' style='border:0'></iframe></div>"
        )

    return (
        f"<!DOCTYPE html><html><head><meta charset=utf-8>"
        f"<title>{project['name']} — GE-GLB</title>{_STYLE}</head>"
        f"<body><a href='/'>← Dashboard</a><h1>{project['name']}</h1>"
        f"<div class=card>"
        f"<p><strong>Source:</strong> {project['source_kind']}</p>"
        f"<p><strong>Status:</strong> {project['status']}</p>"
        f"<p><strong>Trajectory points:</strong> {project['trajectory_points']}</p>"
        f"<p><strong>Image frames:</strong> {project['image_frames']}</p>"
        f"</div>"
        f"{traj_section}"
        f"<div class=card><h2>Products</h2>"
        f"<div class=gallery>{products_html}</div></div>"
        f"</body></html>"
    )


def _pano_viewer_html(name: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=utf-8>"
        f"<title>{name} — 360 Panorama</title>"
        "<style>body{margin:0;background:#000}"
        "#panorama{width:100vw;height:100vh}"
        "a{position:absolute;top:1rem;left:1rem;color:#fff;z-index:10}</style>"
        "<script src='https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js'>"
        "</script>"
        "<link rel=stylesheet "
        "href='https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css'>"
        "</head><body>"
        f"<a href='/project/{name}'>← Back</a>"
        "<div id=panorama></div>"
        "<script>pannellum.viewer('panorama',{"
        "type:'equirectangular',"
        f"panorama:'/static/{name}/product/panorama.png',"
        "autoLoad:true,showControls:true});</script>"
        "</body></html>"
    )


# ── page routes ────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    global _project_cache
    if _scan_root is not None:
        _project_cache = _scan_projects(_scan_root)
    return HTMLResponse(_project_list_html(list(_project_cache.values())))


@app.get("/project/{name}", response_class=HTMLResponse)
async def project_detail(request: Request, name: str):
    info = _get_project(name)
    if info is None:
        return HTMLResponse(f"<h1>Project {name!r} not found</h1>", status_code=404)
    return HTMLResponse(_project_detail_html(info))


@app.get("/project/{name}/pano", response_class=HTMLResponse)
async def pano_viewer(request: Request, name: str):
    return HTMLResponse(_pano_viewer_html(name))


# ── launch helper ──────────────────────────────────────────────────────


def run_server(host: str = "127.0.0.1", port: int = 8080, scan_dir: str = "build") -> None:
    """Configure scan root, mount static files, and start uvicorn."""
    global _scan_root
    import uvicorn

    root = Path(scan_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _scan_root = root
    _scan_projects(root)

    app.mount(
        "/static",
        StaticFiles(directory=str(root), html=True),
        name="static",
    )

    uvicorn.run(app, host=host, port=port, log_level="info")
