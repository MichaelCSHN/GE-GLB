---
id: TICKET-003
title: "Task 03 Drone LookAt — 中性采集计划 + Blender Workflow"
status: active
assignee: "DeepSeek"
created: 2026-07-17
depends_on: [TICKET-001, TICKET-002]
---

## 背景

Task 03（无人机半球 LookAt）已经定义了：
- `DroneLookAtSpec`（半径、方位角、仰角采样）
- `enumerate_hemisphere()`（生成 `HemisphereView` 列表，每个含 ENU 偏移量）

缺失的环节是：将车辆位姿 + 半球偏移量转换为**世界空间的 CameraState**，生成后端无关的采集计划，再连接到 Blender 后端。

这等价于 TICKET-001（中性采集计划）+ TICKET-002（Blender workflow）对 Task 03 的对应物。

## 要求

### 第一部分：中性采集计划（capture_plan.py）

#### 输入

- `DroneLookAtSpec`（半径、方位角列表、仰角列表）
- 车辆位姿列表（`list[VehiclePose]`）
- 相机内参（FOV、分辨率）
- 可选：roll 策略（默认 0）

#### 输出

`CaptureModel`- 风格的 dataclass：

1. **`ordered_states: list[tuple[VehiclePose, CameraState]]`** — 每个车辆位姿 × 每个半球视图 = 一个观察
2. **`entries: list[dict]`** — 每帧采集条目（sequence、camera_id、image path、camera_world）
3. **`calibration: dict`** — 相机标定（LookAt 任务中所有视图共用同一相机模型，内参固定）

#### 关键约束

1. **观察者朝向**：相机始终**朝向车辆中心**（LookAt）。给定观察者在 ENU 中的位置 $(e, n, u)$ 和车辆位姿 $(lon, lat, hdg)$，相机应指向车辆位置。这决定了 `heading_deg` 和 `tilt_deg`。
2. **偏移量坐标系**：`HemisphereView.offset_enu_m` 是**以车辆位置为原点的 ENU 偏移**。观察者的世界坐标 = 车辆 geodetic 位置 + ENU 偏移 → 转换为 geodetic。
3. **相机朝向计算**：
   - 从观察者指向车辆的方向向量 → 计算 heading (atan2) 和 tilt（从 nadir 算）
   - roll 默认为 0
4. **确定性 ID**：同 spec + 同 poses 产生完全相同的 frame/observation IDs
5. **后端无关**：entries 不含 Blender/GE3D 特定字段
6. **camera_id** 格式：`az{azimuth:.0f}_el{elevation:.0f}`

#### 朝向计算数学

```
给定观察者 ENU: (obs_e, obs_n, obs_h)
给定车辆 ENU: (veh_e, veh_n, veh_h)  ← 车辆轨迹对应的 local ENU
给定车辆 geodetic: (veh_lon, veh_lat, veh_hdg)

方向向量: dx = veh_e - obs_e,  dy = veh_n - obs_n,  dz = veh_h - obs_h
heading = degrees(atan2(dx, dy)) % 360     ← KML heading: 从北顺时针
tilt    = degrees(atan2(hypot(dx, dy), -dz)) ← 0=nadir, 90=horizon
```

注意：`enumerate_hemisphere()` 返回的 `offset_enu_m` 是**以车辆为中心**的 ENU 偏移：
- `offset_enu_m[0]` = 东向偏移
- `offset_enu_m[1]` = 北向偏移
- `offset_enu_m[2]` = 向上偏移

观察者在世界 ENU 中的位置 = 车辆在该姿态下的 ENU 位置 + 偏移量。

#### 参考坐标系关系

```
世界 ENU (以第一个轨迹点为原点)
    └── 车辆位置 (geodetic → to_local → ENU)
         └── 半球偏移量 (offset_enu_m)
              └── 观察者位置 (ENU)
                    └── 朝向向量 → 车辆中心
```

#### 默认 spec

```python
def default_spec() -> DroneLookAtSpec:
    return DroneLookAtSpec(
        radius_m=250.0,
        azimuth_deg=(0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0),
        elevation_deg=(30.0, 60.0, 90.0),
    )
```

8 az × 3 el = 24 views per vehicle pose。

### 第二部分：Blender Workflow（workflows/blender.py）

与 TICKET-002 的 `<task>/workflows/blender.py` 模式相同：
1. 调用 `build_capture_model()` 获取 `CaptureModel`
2. 类似 `_write_roof_dataset()` 的函数写入 v1 数据集（manifest/rig/trajectory/frames）—— 不需要 fusion-plan
3. 生成 `blender-job.json`（与 TICKET-002 格式完全一致）
4. 生成 `blender-command.json`
5. 返回 `PlanResult`

## 文件清单

### 第一部分（中性采集计划）

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/tasks/drone_lookat_set/capture_plan.py` | `CaptureModel`、`build_capture_model()`、`default_spec()`、`_lookat_camera_state()`、`_entry()` |

### 第二部分（Blender Workflow）

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/tasks/drone_lookat_set/workflows/__init__.py` | 空包 |
| 新建 | `src/geglb/tasks/drone_lookat_set/workflows/blender.py` | `build_blender_plan()` |
| 新建 | `tests/test_drone_lookat_blender.py` | 测试文件 |

### 修改与导出

| 操作 | 路径 | 说明 |
|------|------|------|
| 修改 | `src/geglb/tasks/drone_lookat_set/__init__.py` | 导出 CaptureModel、build_capture_model、default_spec |

### 禁止修改

- `src/geglb/tasks/drone_lookat_set/{specification,hemisphere,product}.py`
- `src/geglb/products/viewset.py`
- `src/geglb/core/*`
- `scripts/blender_capture.py`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/tasks/roof_360_pano/capture_plan.py` | CaptureModel 模式、calibration 结构、_entry() 函数结构 |
| `src/geglb/tasks/roof_360_pano/workflows/blender.py` | **TICKET-002 产出**——整个 `_write_roof_dataset()` + `build_blender_plan()` 模式可直接复制适配 |
| `src/geglb/tasks/drone_lookat_set/hemisphere.py` | `enumerate_hemisphere()`、`HemisphereView.offset_enu_m` |
| `src/geglb/tasks/drone_lookat_set/specification.py` | `DroneLookAtSpec`、`validate()` |
| `src/geglb/core/camera.py` | `CameraState`、`intrinsics()` |
| `src/geglb/core/trajectory.py` | `VehiclePose` |
| `src/geglb/core/coordinates.py` | `LocalFrame.to_local()` / `to_geodetic()` |
| `src/geglb/core/results.py` | `PlanResult` |

## 测试要求

### capture_plan 测试（tests/test_drone_lookat.py，8 个测试）

- [ ] `test_default_spec_is_valid` — default_spec().validate() 不抛异常
- [ ] `test_observer_count_matches_azimuth_times_elevation` — 默认 8az×3el=24 观察者
- [ ] `test_each_entry_has_correct_camera_id_pattern` — camera_id = `az{...}_el{...}`
- [ ] `test_each_entry_has_camera_world_fields` — 每个 entry 含 camera_id / image / camera_world
- [ ] `test_observer_tilt_points_toward_vehicle` — tilt < 90°，且观察者越高 tilt 越小（越接近 nadir）
- [ ] `test_deterministic_order` — 同 spec 两次运行序列相同
- [ ] `test_heading_changes_with_azimuth` — 对于固定车辆位姿，heading_deg 随 azimuth_deg 变化
- [ ] `test_multi_pose_produces_correct_count` — N 个位姿 × M 个观察者 = N×M 个条目

### Blender workflow 测试（tests/test_drone_lookat_blender.py，6 个测试）

- [ ] `test_generates_valid_blender_job` — 同 TICKET-002 模式
- [ ] `test_dataset_files_written` — manifest/rig/trajectory/frames 齐全
- [ ] `test_camera_world_positions_are_reasonable` — 观察者在 ENU 中的位置与半球半径匹配
- [ ] `test_plan_result_fields` — PlanResult 正确
- [ ] `test_rejects_invalid_scene_file` — 错误路径
- [ ] `test_multi_pose_trajectory` — 多姿态轨迹验证

## 验收标准

- [ ] `python -m unittest tests.test_drone_lookat -v` 8/8 通过
- [ ] `python -m unittest tests.test_drone_lookat_blender -v` 6/6 通过
- [ ] `ruff check src/geglb/tasks/drone_lookat_set/ tests/` 零错误
- [ ] `ruff format --check` 已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 69/69 通过（原 55 + 新增 14）
- [ ] 零新依赖
- [ ] 不修改 core/、scripts/ 和 specification/hemisphere/product

## 设计提示

1. **朝向计算**：`enumerate_hemisphere()` 给的 `offset_enu_m` 是以车辆为中心的偏移量。车辆 ENU 位置用 `LocalFrame.to_local(pose.longitude_deg, pose.latitude_deg)` 计算。观察者 ENU = 车辆 ENU + 偏移量。
2. **相机朝向**：使用 `math.atan2(dx, dy)` 计算 heading（从北顺时针），`math.atan2(h, -dz)` 计算 tilt（tilt=0 是 nadir），其中 `dx = veh_e - obs_e`, `dy = veh_n - obs_n`, `dz = veh_h - obs_h`, `h = hypot(dx, dy)`。
3. **LookAt 任务的特殊性**：所有观察者共享同一个相机模型（FOV 固定），但每个观察者的朝向不同。这意味着 calibration 只需要一个通用相机条目，但每个 entry 的 heading/tilt 不同。
4. **Blender 中的 LookAt**：在 Blender 中，LookAt 通过 `trackTo` constraint 或手动朝向计算实现。`blender_capture.py` 根据 frames 中的 `heading_deg` 和 `tilt_deg` 设置相机朝向即可。
5. **Workflow 代码重用**：TICKET-002 的 `_write_roof_dataset()` 和 `build_blender_plan()` 模式完全可以复制过来修改——换 import、换 `_write_roof_dataset` 为 `_write_lookat_dataset`。
