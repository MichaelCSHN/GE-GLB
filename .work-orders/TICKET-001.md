---
id: TICKET-001
title: "Task 02 Roof 360 — 中性采集计划生成器"
status: closed
assignee: "DeepSeek"
created: 2026-07-17
closed: 2026-07-17
depends_on: []
---

## 背景

Task 02 的产品规范、产品合约和波段定义已就位，但**中性采集计划生成器缺失**——
这是连接 Roof360Spec 与 CaptureBackend（Blender / GE 3D）的关键桥梁。
Task 01 已有 `capture_plan.py` 作为参考模式。

## 要求

### 输入

- Roof360Spec（桅杆高度、水平/向下波段、方位角采样）
- 车辆尺寸（长/宽/高）
- 相机内参（FOV、分辨率）
- 车辆位姿列表（可选，默认单一位姿）

### 输出

CaptureModel dataclass：
1. `ordered_states: list[tuple[VehiclePose, CameraState]]`
2. `entries: list[dict]` — 每帧采集条目
3. `calibration: dict` — 相机标定

### 关键约束

- 相机装在桅杆顶部：(0, 0, bus_height + mast_height) 车辆坐标系
- 坐标系与 SPEC.md 一致
- 水平波段 tilt=90°，向下波段 tilt∈[45°,60°]
- 确定性 ID：同一 spec 产生相同 frame/observation IDs
- 后端无关：entries 不含 Blender/GE3D 特定字段

## 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/tasks/roof_360_pano/capture_plan.py` | CaptureModel、build_capture_model()、default_spec()、validate_band_overlap() |
| 修改 | `src/geglb/tasks/roof_360_pano/__init__.py` | 导出新符号 |
| 新建 | `tests/test_roof_360.py` | 16 个测试 |
| 修改 | `docs/tasks/02-roof-360-pano/README.md` | 更新实现状态 |

### 禁止修改

- `src/geglb/tasks/roof_360_pano/specification.py`
- `src/geglb/products/panorama.py`
- `src/geglb/core/*`
- `schemas/*`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/tasks/underbody_image/capture_plan.py` | CaptureModel 模式、_entry() 结构 |
| `src/geglb/core/camera.py` | CameraState、intrinsics()、camera_to_vehicle_transform() |
| `src/geglb/tasks/roof_360_pano/specification.py` | CaptureBand、Roof360Spec、validate() |
| `src/geglb/core/dataset.py` | write_standard_dataset() 输出格式 |

## 测试要求

- [x] test_default_bands_have_correct_observer_count
- [x] test_tilt_values_match_spec
- [x] test_deterministic_observation_order
- [x] test_each_entry_has_camera_id_and_calibration_reference
- [x] test_overlap_validation
- [x] test_camera_mount_position

## 验收结果

| 标准 | 结果 |
|------|------|
| unittest tests.test_roof_360 -v | 16/16 通过（要求 6 个） |
| ruff check | 零错误 |
| ruff format --check | 5 文件已格式化 |
| compileall -q | 零错误 |
| 全量测试 discover -s tests -v | 46/46 通过 |
| 零新依赖 | ✅ |
