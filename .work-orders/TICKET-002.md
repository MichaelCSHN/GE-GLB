---
id: TICKET-002
title: "Task 02 Roof 360 — Blender 工作流"
status: closed
closed: 2026-07-17
assignee: "DeepSeek"
created: 2026-07-17
depends_on: [TICKET-001]
---

## 背景

中性采集计划 (`build_capture_model()`) 已就绪。下一步将它连接到 Blender 后端——
生成 `blender-job.json`，由 `scripts/blender_capture.py` 在 Blender 无头 Python 运行时消费。
Task 01 已有参考实现：`src/geglb/tasks/underbody_image/workflows/blender.py`

## 要求

### 输入

- Roof360Spec（波段定义）
- 车辆尺寸（长/宽/高）
- 场景 GLB 路径
- 渲染参数（engine、samples、transparent_background）
- 输出目录
- 路线（KML 或 VehiclePose 列表）

### 输出

写入完整的 v1 数据集 + `blender-job.json`（与 Task 01 完全一致的 schema），返回 `PlanResult`。

### 关键约束

1. **`write_standard_dataset()` 不完全兼容**（Roof 360 的 CaptureModel 无 route_points/fusion_plan），需在 workflow 内实现等效写入
2. **用 `PlanResult` 返回**（参考 Task 01）
3. **Scene GLB 验证**（.glb/.gltf 后缀、文件存在性）
4. **不需要 bpy** —— 只生成 JSON
5. **trajectory.jsonl** 从 poses 推导：每个 pose 的 frame_index/distance_m/geodetic/local_enu_m/heading_deg/vehicle_to_world

### blender-job.json frame 格式

```json
{
  "sequence": 0,
  "frame_index": 0,
  "camera_id": "horizontal_az0",
  "image": "images/horizontal_az0/000000.png",
  "status": "planned",
  "ground_truth_only": false,
  "camera_world": {
    "local_enu_m": {"east": 0.0, "north": 0.0, "up": 5.0},
    "heading_deg": 0.0,
    "tilt_from_nadir_deg": 90.0,
    "roll_deg": 0.0,
    "horizontal_fov_deg": 90.0
  }
}
```

## 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/tasks/roof_360_pano/workflows/__init__.py` | 空包 |
| 新建 | `src/geglb/tasks/roof_360_pano/workflows/blender.py` | `build_blender_plan()` |
| 新建 | `tests/test_roof_360_blender.py` | 测试文件 |

### 禁止修改

- `src/geglb/core/*`
- `scripts/blender_capture.py`
- `src/geglb/tasks/roof_360_pano/capture_plan.py`
- `src/geglb/tasks/roof_360_pano/specification.py`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/tasks/underbody_image/workflows/blender.py` | **主参考** — 流程结构、PlanResult、blender-job.json、frames 格式 |
| `src/geglb/core/dataset.py` | write_standard_dataset() 实现、JSONL 读写、_vehicle_to_world() |
| `src/geglb/tasks/roof_360_pano/capture_plan.py` | CaptureModel 结构（无 route_points/fusion_plan） |
| `src/geglb/core/results.py` | PlanResult 用法 |
| `src/geglb/core/trajectory.py` | VehiclePose、resample_route() |

## 测试要求

- [ ] test_generates_valid_blender_job — 生成 job，解析 JSON，逐字段验证
- [ ] test_blender_runner_script_compiles_without_bpy — py_compile 编译验证
- [ ] test_dataset_files_written — manifest/rig/trajectory/frames 均存在且格式正确
- [ ] test_each_frame_has_correct_camera_world — camera_world 字段验证
- [ ] test_plan_result_fields — PlanResult 字段完整性
- [ ] test_rejects_invalid_scene_file — 不存在的 GLB 正确报错

## 验收结果

| 标准 | 结果 |
|------|------|
| unittest tests.test_roof_360_blender -v | 9/9 通过（要求 6 个） |
| ruff check | 零错误 |
| ruff format --check | 3 文件已格式化 |
| compileall -q | 零错误 |
| 全量测试 discover -s tests -v | 55/55 通过 |
| 零新依赖 | ✅ |
| 禁止修改 core/scripts/specification | ✅ |

- [ ] unittest tests.test_roof_360_blender -v 6/6 通过
- [ ] ruff check / format --check 零错误
- [ ] compileall -q 零错误
- [ ] 全量测试 52/52 通过（原 46 + 新增 6）
- [ ] 零新依赖
- [ ] 不修改 core/、scripts/、specification.py

## 设计提示

- `_vehicle_to_world()` 矩阵：参考 `core/dataset.py:36-43`，需复用在 roof workflow 中
- `frames.jsonl` 中 `image` 路径：`images/{camera_id}/{pose_index:06d}.png`
- manifest.json 不需要 `fusion_plan` 字段
- 测试 fixture 可直接实例化 Roof360Spec + VehiclePose 列表，不需要 real KML
