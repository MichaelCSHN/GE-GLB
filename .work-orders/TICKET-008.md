---
id: TICKET-008
title: "geglb serve — 本地 Web 仪表盘"
status: active
assignee: "DeepSeek"
created: 2026-07-18
depends_on: [TICKET-005, TICKET-007]
estimated_hours: 8-12
---

## 背景

GE-GLB 目前完全是 CLI 工具。三任务的管线操作需要用户在目录间手动切换、用外部工具打开 PNG 查看结果、用数字理解空间覆盖。

本工单要求实现 `geglb serve` 命令，启动一个轻量级本地 Web 仪表盘，提供：
1. 项目概览 —— 列出所有构建产物，显示状态
2. 路线可视化 —— 在地图上叠加轨迹和相机锥体
3. 产品画廊 —— 在浏览器中查看车底图像、360 全景、LookAt 缩略图网格

**这是面向 CamoTwin 非编程用户的采集层界面。** 用户不会开命令行，但会点链接。

## 总体架构

```text
浏览器 ←→ FastAPI ←→ 文件系统 (build/ 目录)
                  ↕
            tasks/ 元数据读取
              (现有代码，不做重算)
```

**核心原则**：仪表盘是只读的。不修改数据、不触发渲染、不生成采集计划。只浏览。

## 要求

### 第一部分：依赖与入口

`pyproject.toml` 新增可选依赖 `serve`：

```toml
serve = ["fastapi>=0.115", "uvicorn>=0.34", "folium>=0.19"]
```

CLI 入口（`cli/main.py`）：

```python
serve = commands.add_parser("serve", help="Start the GE-GLB web dashboard")
serve.add_argument("--port", type=int, default=8080)
serve.add_argument("--host", default="127.0.0.1")
serve.add_argument("--dir", default="build", help="Root directory to scan for builds")
```

### 第二部分：后端（`src/geglb/server.py`）

新建 `src/geglb/server.py`，包含一个 FastAPI 应用 + 路由 + 静态文件服务。

**路由清单：**

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 项目列表页（HTML） |
| `/api/projects` | GET | 返回已扫描的 build 目录列表（JSON） |
| `/api/project/{name}` | GET | 返回单个项目的元数据 + 各任务状态（JSON） |
| `/api/project/{name}/trajectory` | GET | 返回轨迹数据 + 用于在地图上渲染的相机锥体 |
| `/api/project/{name}/product/{task}` | GET | 返回产品路径和诊断 |
| `/maps/{name}.html` | GET | Folium 生成的地图页面 |
| `/static/{path}` | GET | 直接服务 build 目录中的图像文件 |

**`/api/projects` 返回格式：**

```json
{
  "projects": [
    {
      "name": "mvp1",
      "has_manifest": true,
      "has_trajectory": true,
      "has_capture": true,
      "has_product": {"underbody": true, "panorama": false, "lookat": false},
      "source_kind": "blender",
      "status": "complete"
    }
  ]
}
```

**`/api/project/{name}` 返回格式：**

```json
{
  "name": "mvp1",
  "manifest": { ... },
  "trajectory_points": 25,
  "image_frames": 100,
  "capture_status": "complete",
  "product_types": ["underbody"],
  "products": {
    "underbody": {
      "exists": true,
      "has_diagnostics": true,
      "coverage": 0.85,
      "image": "/static/mvp1/product/underbody.png"
    }
  }
}
```

### 第三部分：前端页面

所有页面为服务端渲染的 HTML（FastAPI 返回 `HTMLResponse`），未使用前端框架。

#### 页面 1：项目列表（`/`）

- 表格列出所有已扫描的 build 子目录
- 每行显示：项目名、source_kind、帧数、产品状态（红/黄/绿点）
- 点击行跳转到项目详情页

#### 页面 2：项目详情 + 地图（`/project/{name}`）

**上方**：项目信息卡片
- source_kind、帧数、相机数、状态
- 产品清单，每个产品带 "查看" 链接

**中部**：路线地图（内嵌 Folium iframe）
- OpenStreetMap 底图
- 轨迹线（蓝色，带箭头方向）
- 每个采样点的相机锥体（不同相机不同颜色，半透明扇形）
- 支持缩放/平移

**下方**：产品画廊
- Task 01：显示 `underbody.png` + 切换诊断覆盖图
- Task 02：**Pannellum 全景查看器**（拖拽旋转查看）
- Task 03：缩略图网格（点击放大）

#### 页面 3：全景查看（`/project/{name}/pano`）

- Pannellum 查看器全屏嵌入
- 从 `product/panorama.png` 加载

### 第四部分：扫描策略

仪表盘不要求用户"注册项目"。启动时扫描 `--dir` 指定的根目录：

1. 遍历所有一级子目录
2. 检查每个目录是否有 `manifest.json`
3. 如果有，视为一个项目
4. 不递归扫描深层嵌套

`/api/projects` 每次调用**不重新扫描**——在启动时缓存一次。项目详情页可以触发单个项目的重新读取。

### 第五部分：Folium 地图中的相机锥体

```python
import folium
from folium import plugins

m = folium.Map(location=[lat0, lon0], zoom_start=18)

# 轨迹线
folium.PolyLine(
    locations=[(lat, lon) for lat, lon in trajectory],
    color="blue", weight=3, opacity=0.7
).add_to(m)

# 每个采样点的相机锥体（示意）
for pose in poses:
    folium.RegularPolygonMarker(
        location=[pose.lat, pose.lon],
        number_of_sides=3,  # 锥形
        radius=0.5,         # 地面投影半径（米→度近似）
        color=camera_color,
        fill=True,
    ).add_to(m)
```

简化实现：每个采样点画一个 marker，点击显示 camera_id + heading + FOV。不要求精确的 3D 视锥体——扇形示意即可。

### 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/server.py` | FastAPI 应用 + 所有路由 |
| 修改 | `src/geglb/cli/main.py` | 添加 `serve` 子命令 |
| 修改 | `pyproject.toml` | 添加 `serve` 可选依赖 |
| 新建 | `tests/test_server.py` | 测试 |
| 新建 | `src/geglb/templates/project_list.html` | 项目列表模板 |
| 新建 | `src/geglb/templates/project_detail.html` | 项目详情模板 |
| 新建 | `src/geglb/templates/pano_viewer.html` | 全景查看器模板 |

### 禁止修改

- `src/geglb/core/*`
- `src/geglb/tasks/*`
- `src/geglb/products/*`
- `src/geglb/workflows/*`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/core/dataset.py` 的 `validate_dataset()` | 扫描 build 目录时用到的数据解析 |
| `src/geglb/cli/main.py` | CLI 子命令注册模式 |
| `docs/tasks/01-underbody-image/mvp-plan.md` | 了解用户用 CLI 构建产物的流程，确保 GUI 覆盖 |
| `src/geglb/tasks/roof_360_pano/compositor.py` | product 目录结构 |

## 测试要求

`tests/test_server.py`：

- [ ] `test_app_creates`——FastAPI 应用创建成功，test client 可用
- [ ] `test_api_projects_returns_list`——`/api/projects` 返回 200 + JSON 数组
- [ ] `test_api_project_existing`——对已知 build 目录返回 200 + 元数据
- [ ] `test_api_project_not_found`——对未知项目返回 404
- [ ] `test_static_file_serving`——`/static/` 能正常服务图像文件
- [ ] `test_index_page_renders`——`/` 返回 200 + HTML
- [ ] `test_project_page_renders`——`/project/{name}` 返回 200 + HTML

## 验收标准

- [ ] `python -m unittest tests.test_server -v` 7/7 通过
- [ ] `ruff check src/geglb/server.py tests/test_server.py` 零错误
- [ ] `ruff format --check` 已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 113/113 通过（原 106 + 新增 7）
- [ ] 仅新增 `serve` 可选依赖项（fastapi / uvicorn / folium），不修改核心依赖
- [ ] `geglb serve --help` 显示正确的参数

## 关键设计决策

1. **模板 vs JS 框架**：用 FastAPI + Jinja2 模板（后端渲染 HTML），而不是 React/Vue。MVP 不需要 SPA 的复杂性。后续如果需要交互增强，可以用 HTMX 渐进增强。

2. **Folium vs MapLibre**：用 Folium（Python 生成 HTML）。DS 不需要写一行前端 JS 就能产生地图页面。MapLibre 留给 v2。

3. **Pannellum 全景查看器**：一个 `<script>` 标签引入 CDN。不需要 npm/webpack。

4. **静态文件服务**：FastAPI 的 `StaticFiles` mount 到 `/static`，指向 `--dir` 的根目录。图像路径在 JSON API 中以 `/static/{relative_path}` 形式返回。

5. **不修改任何现有代码**（除了 CLI 加一行子命令 + pyproject.toml 加依赖）。server 是一个完全独立的模块。

## 设计提示

1. **测试用 test client**：FastAPI 提供 `TestClient`，不需要真的启动服务器来测试路由。import 后在 `with` 块中用 `client.get("/")`。

2. **Folium 地图保存为 HTML**：`m.save(str(output_dir / "map.html"))`，然后在项目详情页中用 `<iframe src="/maps/{name}.html">` 嵌入。

3. **Pannellum CDN**：`https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/`，不需要打包到项目中。

4. **简化图像服务**：对 build 目录 mount `StaticFiles` 时，指定 `html=True` 以支持目录索引和 SPA fallback。

5. **项目扫描状态**：先读 `manifest.json` 判断是否存在。然后尝试读 `product/manifest.json` 确定可用产品。
