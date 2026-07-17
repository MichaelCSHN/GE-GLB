---
id: TICKET-009
title: "geglb run — 端到端整合管线 + v2 CLI 入口"
status: active
assignee: "DeepSeek"
created: 2026-07-18
depends_on: [TICKET-001, TICKET-002, TICKET-003, TICKET-004, TICKET-005, TICKET-006, TICKET-007, TICKET-008]
estimated_hours: 8-10
---

## 背景

当前八张工单已经建成了 GE-GLB 的全部模块，但它们是**分散的零件**：

| 模块 | 入口 |
|------|------|
| 三任务采集计划 | `geglb blender plan` / `ge-pro plan` |
| 三任务 v2 写入器 | 仅 Python API（`blender_v2.py`），无 CLI |
| 三任务产品输出 | `geglb product underbody`（仅 Task 01 有 CLI） |
| 全景拼接 | `geglb stitch run` |
| 产品验证 | `geglb validate-product` |
| 仪表盘 | `geglb serve` |

用户需要一个**统一的入口**来完成从计划到产品的全流程。

## 要求

### 第一部分：产品 CLI 补全

当前只有 Task 01 有 `geglb product underbody` 子命令。补全另外两个：

```powershell
geglb product underbody --dataset <dir> --target-frame <N> --out <dir>
geglb product panorama --dataset <dir> --out <dir> [--width <px>]
geglb product lookat --dataset <dir> --out <dir>
```

对应函数调用：

| CLI | 函数 | 所在文件 |
|-----|------|---------|
| `product underbody` | `produce_underbody_product()` | `evaluation.py` |
| `product panorama` | `build_panorama()` | `roof_360_pano/compositor.py` |
| `product lookat` | `write_viewset_product()` | `drone_lookat_set/product_writer.py` |

全景命令可选参数：`--width`（默认 640）、`--track-source`（默认 false）。

### 第二部分：`geglb run` 端到端单命令

`geglb run` 是一个高阶编排命令，在一个执行中依次调用：

```
plan → [user runs Blender] → composite → product → validate
```

**命令行签名：**

```powershell
geglb run underbody --config <toml> --route <kml> --scene <glb> --out <dir>
geglb run panorama --spec <spec> --scene <glb> --out <dir>
geglb run lookat --spec <spec> --scene <glb> --out <dir>
```

**执行流程（以 underbody 为例）：**

```
1. Plan:     build_blender_plan()               → write blender-job.json + dataset
2. Render:   打印下一步命令给用户，不自动执行 Blender
3. Composite: run_planar_stitcher()              → write bev images
4. Product:  produce_underbody_product()         → write product/
5. Validate: validate_product("underbody")       → print report
```

**关键设计**

- **步骤 2 渲染不自动执行 Blender**：打印提示让用户手动运行，因为 Blender 不在 Python 进程中。
  但增加 `--blender-exec` 可选参数。如果提供，自动 `subprocess.run()` 调用 Blender。
- **每步结果写入 `run.json`**：v2 格式的 `execution` 块追踪每步状态。
- **可恢复**：如果 `--resume`，跳过已完成的步骤（检查 `run.json` 或产物文件存在性）。
- **输出目录结构**（混合 v1 + v2 兼容）：

```
out/
├── run.json              ← 执行追踪（v2 格式）
├── blender-job.json      ← plan 产出
├── blender-command.json  ← 用户可复制粘贴
├── manifest.json         ← v1 数据集 manifest
├── (其他 v1 文件)
├── product/              ← 产品输出
│   ├── manifest.json
│   └── underbody.png / diagnostics/
└── logs/
    └── run.log
```

**`run.json` 格式：**

```json
{
  "schema_version": "ge-glb.run/v1",
  "task_id": "task01_underbody",
  "steps": {
    "plan": {"status": "complete", "outputs": ["blender-job.json"]},
    "render": {"status": "pending", "note": "run: blender --background --python scripts/blender_capture.py -- --job blender-job.json"},
    "composite": {"status": "skipped", "reason": "render not complete"},
    "product": {"status": "skipped"},
    "validate": {"status": "skipped"}
  },
  "execution": {
    "started_at": "...",
    "completed_at": null
  }
}
```

**参数传递规则：**

| task 参数 | underbody | panorama | lookat |
|-----------|-----------|----------|--------|
| `--config` | ✅ 必须 | ❌ | ❌ |
| `--route` | ✅ 必须 | ❌ | ❌ |
| `--scene` | ✅ 必须 | ✅ 必须 | ✅ 必须 |
| `--spec` | ❌ | ✅ 必须（TOML 文件路径） | ✅ 必须（TOML 文件路径） |
| `--out` | ✅ 必须 | ✅ 必须 | ✅ 必须 |
| `--blender-exec` | 可选 | 可选 | 可选 |
| `--resume` | 可选 | 可选 | 可选 |

### 第三部分：Task 配置 TOML 格式

全景和 LookAt 目前没有自己的 TOML 配置。新建示例配置：

**`examples/02-roof-360-pano/default.toml`：**

```toml
[project]
name = "roof-360-demo"

[bus]
length_m = 12.0
width_m = 2.55
height_m = 3.20

[spec]
mast_height_m = 2.0

[[spec.bands]]
band_id = "horizontal"
tilt_from_nadir_deg = 90.0
azimuth_deg = [0.0, 90.0, 180.0, 270.0]

[[spec.bands]]
band_id = "downward"
tilt_from_nadir_deg = 50.0
azimuth_deg = [0.0, 90.0, 180.0, 270.0]

[capture]
image_width = 1920
image_height = 1080
horizontal_fov_deg = 90.0
```

**`examples/03-drone-lookat-set/default.toml`：**

```toml
[project]
name = "lookat-demo"

[spec]
radius_m = 250.0
azimuth_deg = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]
elevation_deg = [30.0, 60.0, 90.0]

[capture]
image_width = 1920
image_height = 1080
horizontal_fov_deg = 90.0
```

在新建 `src/geglb/core/config_v2.py` 中增加对应的 TOML 加载器：

```python
@dataclass(frozen=True)
class RunConfig:
    task: str
    project_name: str
    bus: BusConfig | None  # 仅 underbody 和 panorama 需要
    spec: dict[str, object]  # task 特有的 spec 参数
    capture: CaptureConfig

def load_run_config(path: str | Path) -> RunConfig: ...
```

### 第四部分：v2 CLI 入口

现有的 `blender_v2.py` 工作流（TICKET-005 产出）没有 CLI 入口。为三任务添加：

```powershell
geglb blender plan-v2 --config <toml> --route <kml> --scene <glb> --out <dir>
```

调用 `build_blender_plan_v2()` 生成 v2 运行目录。输出简要 summary。

### 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/core/config_v2.py` | `RunConfig` + `load_run_config()` + TOML 解析 |
| 新建 | `src/geglb/workflows/runner.py` | `run_task()`——端到端编排函数 |
| 修改 | `src/geglb/cli/main.py` | 添加 `run` 子命令 + `product panorama/lookat` + `blender plan-v2` |
| 新建 | `examples/02-roof-360-pano/default.toml` | 全景默认配置 |
| 新建 | `examples/03-drone-lookat-set/default.toml` | LookAt 默认配置 |
| 新建 | `tests/test_runner.py` | 单元测试 + 集成测试 |
| 新建 | `tests/test_config_v2.py` | 配置加载测试 |

### 禁止修改

- `src/geglb/tasks/*/`（仅增加 TOML 配置文件，不碰 Python 代码）
- `src/geglb/products/*`
- `src/geglb/core/{dataset,dataset_v2,hashing}.py`
- `src/geglb/server.py`
- `schemas/*`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/cli/main.py` | 子命令注册模式、参数传递方式 |
| `src/geglb/tasks/underbody_image/workflows/blender.py` | v1 workflow 结构 |
| `src/geglb/tasks/underbody_image/workflows/blender_v2.py` | v2 workflow 结构（TICKET-005 产出） |
| `src/geglb/tasks/underbody_image/evaluation.py` | `produce_underbody_product()` 签名 |
| `src/geglb/tasks/roof_360_pano/compositor.py` | `build_panorama()` 签名 |
| `src/geglb/tasks/drone_lookat_set/product_writer.py` | `write_viewset_product()` 签名 |
| `src/geglb/products/validate.py` | `validate_product()` 签名 |
| `src/geglb/core/config.py` | `load_config()` TOML 加载模式 |

## 测试要求

### `test_config_v2.py`

- [ ] `test_load_run_config_underbody`——加载 underbody TOML，验证 task/bus/capture 字段
- [ ] `test_load_run_config_panorama`——加载全景 TOML，验证 spec.mast_height 和 bands
- [ ] `test_load_run_config_lookat`——加载 LookAt TOML，验证 spec.radius 和 azimuth/elevation
- [ ] `test_rejects_invalid_task`——无效 task 名称报错

### `test_runner.py`

- [ ] `test_run_plan_only`——使用 `geglb run underbody`（不自动 Blender），验证 plan 步骤状态为 complete，render 为 pending
- [ ] `test_run_resume`——再次带 `--resume` 运行同一目录，plan 步骤跳过（已 complete）
- [ ] `test_run_with_subprocess_blender`——指定 `--blender-exec`，验证 subprocess 被调用（mock 或不存在的 exe 的错误处理）
- [ ] `test_run_product_and_validate`——在已有数据集上运行 `composite→product→validate` 三步

### CLI smoke

- [ ] `test_product_panorama_cli`——直接调用 `geglb product panorama --dataset <dir> --out <dir>`，验证产物文件存在
- [ ] `test_product_lookat_cli`——同上
- [ ] `test_blender_plan_v2_cli`——调用 `geglb blender plan-v2 ...`，验证输出包含 v2 run 目录

## 验收标准

- [ ] `python -m unittest tests.test_config_v2 -v` 4/4 通过
- [ ] `python -m unittest tests.test_runner -v` 4/4 通过
- [ ] CLI smoke 3/3 通过
- [ ] `ruff check` 零错误
- [ ] `ruff format --check` 已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 124/124 通过（原 113 + 新增 11）
- [ ] 零新核心依赖（`run` 子命令不需要额外 pip 包）

## 设计提示

1. **runner.py 不做 Blender 自动重试**——只负责 `subprocess.run(blender_cmd)`，成功或失败都记录到 run.json。重试逻辑是用户手动重新 `--resume`。
2. **步骤状态机**：`pending → running → complete / failed / skipped`。只有前一步 complete 后一步才执行。`skipped` = 前一步未完成或 `--resume` 检测到这一步已 complete。
3. **run.json 的持久化**：每步开始前写 `running`，完成后改写为 `complete` 或 `failed`。这样即使中途崩溃，重读 run.json 也能知道哪里断了。
4. **全景/LookAt 的 spec 参数**：指定 `--spec examples/02-roof-360-pano/default.toml`（TOML 文件路径）。runner 读取后实例化 `Roof360Spec`/`DroneLookAtSpec`。
5. **`run` 的三种模式**：
   - `geglb run underbody --config ... --route ... --scene ... --out dir`（完整端到端）
   - `geglb run underbody --existing dir`（跳过 plan，从已有数据集开始 composite）
   - `geglb run underbody --existing dir --resume`（继续之前中断的运行）
