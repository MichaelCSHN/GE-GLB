---
id: TICKET-004
title: "Task 02 Roof 360 — 全景拼接处理器与产品输出"
status: active
assignee: "DeepSeek"
created: 2026-07-17
depends_on: [TICKET-002]
---

## 背景

Task 02 目前可以**规划和采集**（capture_plan + Blender workflow），但缺少从采集数据到最终产品的核心拼图——**球形全景拼接器**。

Task 01 有等效的 `compositor.py` + `evaluation.py` 作为参考模式：
- `compositor.py`：平面 IPM 拼接基线（将多视角图像投射到地面并加权融合）
- `evaluation.py`：真值对比 + UnderbodyImageProduct 输出

Task 02 需要一个镜像实现：将水平和向下两个波段的图像投影到球面空间，融合为一张等距柱状投影（equirectangular）`panorama.png`。

## 要求

### 输入

- 一个已完成采集的 Roof 360 标准 v1 数据集（包含 `frames.jsonl`、`rig.json`、`trajectory.jsonl`）
- 参数：输出分辨率（宽度，单位像素）、保留无效区域的 alpha 掩膜

### 输出

1. `panorama.png`——等距柱状投影图像，RGBA（无效区域 alpha=0）
2. `diagnostics/validity.png`——有效性掩膜（灰度图，白色=有效覆盖）
3. `diagnostics/coverage.png`——覆盖图（灰度图，每个像素的观察者计数归一化）
4. `result.json`——拼接结果 manifest（schema、算法、参数、覆盖率统计）
5. （可选）`diagnostics/seam-map.png`——接缝图（每个像素标注来自哪个观察者）

### 算法

#### 1. 坐标映射：像素 → 球面方向

将等距柱状投影中的像素 `(px, py)`（宽度 W，高度 H）映射为球面方向向量：

```
lon = 2π * px / W          ← 经度（环绕水平方向）
lat = π/2 - π * py / H     ← 纬度（-π/2 底部，+π/2 顶部）
                            H 应 = W / 2，但允许非标准比例
x = cos(lat) * cos(lon)
y = cos(lat) * sin(lon)
z = sin(lat)
```

#### 2. 球面方向 → 观察者相机坐标

对每个观察者的 `camera_world`（已知 heading_deg、tilt_deg、roll_deg、horizontal_fov_deg），
构建从世界坐标系到相机坐标系的变换。

已知：
- 相机在 ENU 世界中的朝向由 heading(θ)、tilt(φ)、roll(ρ) 定义
- heading、tilt、roll 为欧拉角（内旋 Z→Y'→X''？不同约定导致不同结果）

建议用以下方式构造旋转矩阵：

**Step 1**：从 heading/tilt/roll 计算相机的局部坐标系轴（世界坐标系中）。

相机朝向由 SPEC.md 约定：相机 z 轴向前（指向观察方向），x 向右，y 向下。

计算相机 z 轴（观察方向）：
```
z_axis_x = sin(heading) * sin(tilt)
z_axis_y = cos(heading) * sin(tilt)
z_axis_z = -cos(tilt)
```

计算相机 x 轴（未 roll 时朝右）：
```
x_axis_x = cos(heading)
x_axis_y = -sin(heading)
x_axis_z = 0.0
```

计算相机 y 轴（未 roll 时朝下）= z × x：
```
y_axis = cross(z_axis, x_axis)  (= z_axis × x_axis)
```

然后应用 roll（绕 z 轴旋转）：
```
x_axis_rolled = x_axis * cos(roll) + y_axis * sin(roll)
y_axis_rolled = -x_axis * sin(roll) + y_axis * cos(roll)
```

**Step 2**：将世界方向向量 (wx, wy, wz) 变换到相机坐标系：

```
cam_x = dot(world_vec, x_axis_rolled)
cam_y = dot(world_vec, y_axis_rolled)
cam_z = dot(world_vec, z_axis)
```

**Step 3**：从相机坐标计算像素位置：

```
if cam_z <= 0:  # 在相机后方
    该像素无效
px = fx * cam_x / cam_z + cx
py = fy * cam_y / cam_z + cy
```

其中 (fx, fy, cx, cy) 从校准中获取。

#### 3. 融合策略

对于每个等距柱投影像素，可能被多个观察者覆盖：

- **最新观察优先**：在多帧采集时，可用帧号或 `sequence` 决定，或使用简单平均
- **加权融合**：按入射角（grazing angle）加权，观察方向与表面法线夹角越小权重越高。
  对于球面投影，所有像素在球面上的法线就是其方向向量本身，因此
  `weight = dot(camera_z, pixel_normal)`（当结果为正时）。
- **有效性检测**：无任何有效观察的像素 alpha=0

#### 4. 简化实现（初始基线）

与 Task 01 的 `compositor.py` 一样，第一版可以做简化假设：
- 等距柱投影映射（无柱面校正、无畸变校正）
- 直接最近邻采样（不做双线性/三次插值）
- 简单平均或加权融合（不做接缝优化、曝光补偿）
- 结果 manifest 中声明已知局限

### 产品输出

与 Task 01 的 `evaluation.py` 模式相同，写 `Panorama360Product` manifest。

**注意**：Task 02 没有"nadir ground truth"，所以 `evaluation.py` 风格的真值对比不适用。
但是应报告：总体覆盖率（有效像素/总像素）、各波段贡献统计。

### 关键约束

1. **后端无关**：只读标准 v1 数据集，不含 Blender-specific 路径
2. **仅 numpy+PIL**：与 Task 01 的 compositor 相同的依赖策略
3. **不多不少**：不制造虚假全景覆盖（alpha=0 表示无数据），不裁切全景
4. **稳定性**：相同输入数据集产生完全相同的像素输出
5. **局限性声明**：明确列出已知局限

## 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/tasks/roof_360_pano/compositor.py` | `build_panorama()`——球形投影 + 融合 + 产品输出 |
| 新建 | `tests/test_roof_360_compositor.py` | 测试文件 |
| 修改 | `src/geglb/tasks/roof_360_pano/__init__.py` | 导出新符号 |

### 禁止修改

- `src/geglb/products/panorama.py`
- `src/geglb/tasks/roof_360_pano/{specification,capture_plan,workflows}.py`
- `src/geglb/core/*`
- `scripts/*`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/tasks/underbody_image/compositor.py` | **主参考**——warp 循环、权重计算、limitations 声明模式、manifest 结构 |
| `src/geglb/tasks/underbody_image/evaluation.py` | 产品写入模式（产品 manifest、诊断输出） |
| `src/geglb/core/camera.py` | `camera_to_vehicle_transform()`——理解 heading/tilt/roll → 旋转矩阵 |
| `src/geglb/core/dataset.py` | `read_jsonl()`、`validate_dataset()` |
| `src/geglb/products/panorama.py` | `Panorama360Product`——最终产品格式 |
| `schemas/products/panorama-360.schema.json` | 产品 schema |

## 测试要求

`tests/test_roof_360_compositor.py`：

- [ ] `test_panorama_output_dimensions`——给定 W=640、H=320、已知输入，输出尺寸正确
- [ ] `test_panorama_has_alpha_channel`——RGBA 模式，无效区域 alpha=0
- [ ] `test_known_pixel_maps_to_correct_source`——沿水平方向的一个狭窄 FOV 输入只在对应的经度范围产生有效像素
- [ ] `test_deterministic_output`——同输入两次运行输出完全一致
- [ ] `test_limitations_declared_in_manifest`——result.json 包含 limitations 数组
- [ ] `test_rejects_incomplete_dataset`——缺少图像的时报错（与 Task 01 相同模式）
- [ ] `test_full_coverage_with_synthetic_data`——用合成的全包围测试图案验证覆盖率 100%

## 验收标准

- [ ] `python -m unittest tests.test_roof_360_compositor -v` 7/7 通过
- [ ] `ruff check src/geglb/tasks/roof_360_pano/compositor.py tests/test_roof_360_compositor.py` 零错误
- [ ] `ruff format --check` 已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 77/77 通过（原 70 + 新增 7）
- [ ] 零新依赖
- [ ] 不修改 core/、scripts/、specification

## 设计提示

1. **先索引后渲染**：构建一个"每个观察者→它的世界方向→相机空间投影"的完整索引，再用索引查询逐像素渲染。避免在像素循环中反复解析 JSON。
2. **球面采样**：等距柱投影在极点附近过度采样（经度线汇聚）。对极地地区，可以降低 azimuth 采样密度，但首次实现不做优化——保持均匀网格。
3. **测试数据生成**：用已知颜色填充测试图像（例如红色水平波段、蓝色向下波段），然后验证全景中对应区域的颜色正确。
4. **内外参**：使用 `rig.json` 中的 `camera_to_vehicle` 矩阵和 `intrinsics`，而不是重新计算。
5. **从 `frames.jsonl` 获取信息**：每帧的 `camera_world` 包含了 `heading_deg`、`tilt_from_nadir_deg`、`roll_deg`、`horizontal_fov_deg`，`image` 包含相对路径。
