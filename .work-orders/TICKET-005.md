---
id: TICKET-005
title: "CaptureDataset v2 共享运行布局 + 追溯性写入器"
status: active
assignee: "DeepSeek"
created: 2026-07-18
depends_on: [TICKET-001, TICKET-002, TICKET-003, TICKET-004]
estimated_hours: 6-10
---

## 背景

当前三个 Task 各自独立地写 `ge-glb.dataset/v1` 数据集：

| Task | writer | 位置 |
|------|--------|------|
| Task 01 | `core.dataset.write_standard_dataset()` | `src/geglb/core/dataset.py` |
| Task 02 | `workflows/blender.py::_write_roof_dataset()` | 内联在 workflow 中 |
| Task 03 | `workflows/blender.py::_write_lookat_dataset()` | 内联在 workflow 中 |

三个 writer 有大量重复代码，且 `v1` 格式没有：
- **统一的 task 标识**（v1 manifest 的 `project` 字段是自由文本字符串）
- **内容哈希**（无法验证数据完整性）
- **源码追溯**（无法从数据反查生成它的代码版本、配置、时间）
- **resumable 状态**（中断后无法知道哪些帧已完成）

SPEC.md 和 `schemas/capture/capture-dataset-v2.schema.json` 已经定义了目标 v2 格式的骨架。
PLAN.md 中对应的条目是：

> `[ ] Introduce ge-glb.capture-dataset/v2 alongside the v1 compatibility writer.`
> `[ ] Add run-level provenance, content hashes, and resumable execution state.`

本工单要求实现 **v2 写入器** + **追溯性元数据**，同时保留 v1 写入器不动。

## 要求

### 第一部分：v2 CaptureDataset 写入器

#### 设计

新建 `core/dataset_v2.py`，实现 `write_capture_dataset_v2()` 函数。

v2 运行目录布局（来自 SPEC.md）：

```
run/
├─ run.json                 ← 运行元数据（时间、版本、git commit、配置）
├─ capture-plan.json        ← 中性采集计划（与现有格式一致）
├─ capture/
│  ├─ manifest.json         ← 更新后的 v2 manifest
│  ├─ rigs/                 ← 标定数据
│  │  └─ rig.json
│  ├─ trajectories/         ← 轨迹数据
│  │  └─ trajectory.jsonl
│  ├─ observations.jsonl    ← 每帧观测 + camera_to_world
│  └─ images/               ← 图像文件（与现有目录结构一致）
├─ product/                 ← 任务特定产品输出
├─ diagnostics/             ← 诊断文件
└─ logs/                    ← 运行时日志
```

**`run.json` 格式：**

```json
{
  "schema_version": "ge-glb.run/v2",
  "task_id": "task01_underbody",
  "created_at": "2026-07-18T12:00:00Z",
  "geglb_version": "0.3.0",
  "git_commit": "abc123def456",
  "source": {
    "kind": "blender",
    "adapter": "blender_python",
    "scene_glb": "path/to/scene.glb"
  },
  "configuration": {
    "capture_spacing_m": 0.5,
    "image_width": 1920,
    "image_height": 1080
  },
  "provenance": {
    "hashes": {
      "manifest.json": "sha256:...",
      "observations.jsonl": "sha256:..."
    },
    "dependencies": [
      {"path": "scene.glb", "hash": "sha256:...", "role": "scene_geometry"},
      {"path": "route.kml", "hash": "sha256:...", "role": "trajectory_input"}
    ]
  },
  "execution": {
    "status": "complete",
    "started_at": "2026-07-18T11:55:00Z",
    "completed_at": "2026-07-18T12:00:00Z",
    "frames_total": 100,
    "frames_captured": 100,
    "frames_failed": 0
  }
}
```

**v2 manifest 格式（`capture/manifest.json`）：**

```json
{
  "schema_version": "ge-glb.capture-dataset/v2",
  "task": {
    "task_id": "task01_underbody",
    "product_schema": "ge-glb.product.underbody-image/v1"
  },
  "source": {
    "mode": "virtual",
    "backend": "blender"
  },
  "status": "planned",
  "files": {
    "rigs": ["rigs/rig.json"],
    "trajectories": ["trajectories/trajectory.jsonl"],
    "observations": "observations.jsonl",
    "images_root": "images/"
  }
}
```

**`observations.jsonl` 格式（与现有 `frames.jsonl` 兼容的扩展版）：**

```json
{
  "observation_id": "task01_underbody/000005/front",
  "sequence": 20,
  "frame_index": 5,
  "camera_id": "front",
  "image": "images/front/000005.png",
  "status": "planned",
  "ground_truth_only": false,
  "camera_world": {
    "local_enu_m": {"east": 1.23, "north": 4.56, "up": 3.05},
    "heading_deg": 0.0,
    "tilt_from_nadir_deg": 50.0,
    "roll_deg": 0.0,
    "horizontal_fov_deg": 100.0
  },
  "camera_to_world": [
    [0.0, -1.0, 0.0, 1.23],
    [1.0, 0.0, 0.0, 4.56],
    [0.0, 0.0, 1.0, 3.05],
    [0.0, 0.0, 0.0, 1.0]
  ],
  "image_hash": "sha256:abcdef..."
}
```

其中 `camera_to_world` 字段是**新增的**。它提供了 4×4 齐次矩阵形式的世界变换，
与现有的 `camera_world` 中的 heading/tilt/roll 并存。

#### 函数签名

```python
def write_capture_dataset_v2(
    output_dir: str | Path,
    task_id: str,
    product_schema: str,
    source_kind: str,
    source_backend: str,
    source_metadata: dict[str, object],
    model: object,  # CaptureModel 实例（三个 Task 的类型一致）
    config_snapshot: dict[str, object],
    dependency_hashes: dict[str, str],  # 输入文件路径 → SHA256
) -> dict[str, object]: ...
```

返回值至少包含：`run_dir`、`status`、文件列表和哈希。

### 第二部分：v1 兼容性

- `write_capture_dataset_v2()` 是**新函数**，不动现有的 `write_standard_dataset()`。
- v1 写入器和验证器保持不变。
- 在 `core/dataset.py` 中加一个 `DATASET_V2_SCHEMA = "ge-glb.capture-dataset/v2"` 常量。

### 第三部分：内容哈希

实现 `core/hashing.py` 模块：

```python
def file_sha256(path: str | Path) -> str:
    """返回文件的 SHA-256 十六进制摘要。"""

def dir_sha256(path: str | Path) -> dict[str, str]:
    """返回目录中所有文件的相对路径→SHA256 映射。"""
```

用于在 `run.json` 的 `provenance.hashes` 中记录每个输出文件的完整性校验值。

### 第四部分：Resumable 状态

在 `run.json` 的 `execution` 块中，帧级别状态通过 `observations.jsonl` 中的 `status` 字段跟踪：

| 状态 | 含义 |
|------|------|
| `planned` | 已规划但未采集 |
| `captured` | 图像文件存在且通过完整性检查 |
| `failed` | 采集中发生错误 |
| `skipped` | 由于依赖缺失跳过 |

当 `execution.status = "incomplete"` 时，后续运行应：
1. 读取 `observations.jsonl` 识别所有 `planned` 和 `failed` 帧
2. 仅处理这些未完成的帧
3. 更新状态并重写 `run.json`

### 第五部分：Task Workflow 更新

为每个 Task 的 Blender workflow 添加一个 `build_blender_plan_v2()` 函数，
调用新的 `write_capture_dataset_v2()` 写入 v2 运行目录，然后在此基础上生成
`blender-job.json`。

具体来说：

| 操作 | 文件 |
|------|------|
| **新建** | `src/geglb/core/dataset_v2.py` — v2 写入器 |
| **新建** | `src/geglb/core/hashing.py` — 哈希工具 |
| **修改** | `src/geglb/core/dataset.py` — 添加 `DATASET_V2_SCHEMA` 常量 |
| **新建** | `src/geglb/tasks/underbody_image/workflows/blender_v2.py` |
| **新建** | `src/geglb/tasks/roof_360_pano/workflows/blender_v2.py` |
| **新建** | `src/geglb/tasks/drone_lookat_set/workflows/blender_v2.py` |
| **新建** | `tests/test_dataset_v2.py` |
| **新建** | `tests/test_hashing.py` |

每个 `blender_v2.py` 应：
1. 调用 `build_capture_model()`（已有）
2. 调用 `write_capture_dataset_v2()` 写入 v2 运行目录
3. 从 `observations.jsonl` 读取帧数据
4. 生成 `blender-job.json`（与 v1 版本格式完全一致）
5. 更新 `run.json` 中的 `execution` 状态
6. 返回 `PlanResult`

### 注意事项

**Git commit 检测**：`run.json` 中的 `git_commit` 应尝试从 `.git/HEAD` 和 `.git/refs/` 读取。
如果 `.git` 不可用（非开发环境部署），则用 `"unknown"` 填充。

**依赖哈希**：`dependency_hashes` 包括场景 GLB、KML 路线、TOML 配置等文件的哈希。
这些由调用者提供（因为 workflow 知道自己的输入文件），v2 写入器负责记录。

**v1 不动**：所有现有 v1 代码原封不动。v2 是额外写入路径。

## 禁止修改

- `src/geglb/core/dataset.py`（仅加一行常量 `DATASET_V2_SCHEMA`）
- `src/geglb/core/interfaces.py`、`results.py`、`config.py`
- `src/geglb/tasks/*/capture_plan.py`
- `src/geglb/tasks/*/specification.py`
- `src/geglb/tasks/*/compositor.py`
- `src/geglb/products/*`
- `scripts/*`
- `schemas/*`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/core/dataset.py` | v1 写入器结构（`write_standard_dataset`、`validate_dataset`、`write_json`、`write_jsonl`、`read_jsonl`） |
| `src/geglb/core/results.py` | `PlanResult` 用法（v2 workflow 也要用它返回） |
| `schemas/capture/capture-dataset-v2.schema.json` | v2 manifest 的 JSON Schema |
| `src/geglb/tasks/roof_360_pano/workflows/blender.py` | Task 02 v1 workflow（_write_roof_dataset 内联写入模式） |
| `src/geglb/tasks/underbody_image/workflows/blender.py` | Task 01 v1 workflow（使用 write_standard_dataset 模式） |
| `SPEC.md`（运行布局部分） | v2 run 目录结构定义 |

## 测试要求

### `test_hashing.py`

- [ ] `test_file_sha256_deterministic` — 同一文件两次哈希相同
- [ ] `test_file_sha256_differs_for_different_content` — 不同内容哈希不同
- [ ] `test_dir_sha256_returns_relative_paths` — 目录哈希的键是相对路径

### `test_dataset_v2.py`

- [ ] `test_writes_all_required_files` — 运行目录包含 run.json、capture-plan.json、capture/manifest.json 等
- [ ] `test_run_json_has_provenance` — run.json 包含 hashes、dependencies、git_commit
- [ ] `test_run_json_has_execution_block` — run.json 包含 execution 块（status、timestamps）
- [ ] `test_observations_have_camera_to_world` — observations.jsonl 每条包含 camera_to_world 矩阵
- [ ] `test_images_root_directory_exists` — images/ 目录存在
- [ ] `test_v2_does_not_modify_v1` — 调用 v2 写入器后 v1 文件不变
- [ ] `test_resumable_status_round_trip` — 修改 observation status 后重新加载，状态保持

### Task v2 workflow tests

- [ ] `test_task01_v2_workflow` — 调用 Task 01 的 `build_blender_plan_v2()`，验证 run.json
- [ ] `test_task02_v2_workflow` — 同上
- [ ] `test_task03_v2_workflow` — 同上

## 验收标准

- [ ] `python -m unittest tests.test_hashing -v` 3/3 通过
- [ ] `python -m unittest tests.test_dataset_v2 -v` 7/7 通过
- [ ] 三个 Task 的 `test_*_v2_workflow` 各 1 个，共 3/3 通过
- [ ] `ruff check src/geglb/core/dataset_v2.py src/geglb/core/hashing.py tests/test_*.py` 零错误
- [ ] `ruff format --check` 全部已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 90+/90+ 通过（原 77 + 新增 ~13），零破坏
- [ ] 零新依赖
- [ ] v1 代码完全不受影响
