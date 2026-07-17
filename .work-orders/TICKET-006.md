---
id: TICKET-006
title: "Task 03 Drone LookAt — 产品输出生成器（viewset + thumbnails + contact sheet）"
status: active
assignee: "DeepSeek"
created: 2026-07-18
depends_on: [TICKET-003]
estimated_hours: 4-6
---

## 背景

三个 Task 的产品输出管线目前：

| Task | 产品模块 | 主产物 | 诊断 |
|------|---------|--------|------|
| 01 | `evaluation.py` | `underbody.png` | confidence/coverage/source-map |
| 02 | `compositor.py` | `panorama.png` | validity/coverage/seam-map |
| 03 | **缺失** ❌ | `viewset.json` | 无 |

Task 03 的采集计划（capture_plan）和 Blender workflow 已完成，渲染输出的图像就在
`images/{camera_id}/*.png` 中。但缺少一个模块将原始图像和元数据组装为最终产品。

PLAN.md 中对应的条目：

> `[ ] Build viewset.json, thumbnails, contact sheet, and completeness metrics.`

## 要求

### 输入

一个已完成采集且验证通过的 Task 03 v1 数据集，包含：

- `manifest.json` / `rig.json` / `frames.jsonl`（标准 v1）
- `images/az0_el30/000000.png` 等渲染输出图像
- 每帧包含 `camera_id`（格式 `az{azimuth}_el{elevation}`）、`camera_world`、`image` 路径

### 输出

写入一条完整的 LookAtViewSet 产品目录：

```
product/
├─ viewset.json          ← 主产品 manifest（LookAtViewSetProduct schema）
├─ diagnostics/
│  ├─ thumbnails/        ← 每个视图的缩略图（128px 宽，保持比例）
│  ├─ contact-sheet.png  ← 所有缩略图的二维网格拼图
│  └─ completeness.json  ← 覆盖率统计
└─ manifest.json         ← 产品清单
```

#### viewset.json 格式

严格遵循 `LookAtViewSetProduct` 的 `as_dict()` 输出格式：

```json
{
  "product_schema": "ge-glb.product.lookat-viewset/v1",
  "task_id": "task03_drone_lookat",
  "capture_dataset": "../capture",
  "primary_artifact": "viewset.json",
  "views": [
    {
      "image": "images/az0_el30/000000.png",
      "azimuth_deg": 0.0,
      "elevation_deg": 30.0,
      "radius_m": 250.0,
      "target_ref": "vehicle_center"
    }
  ]
}
```

views 数组的顺序必须**确定性**：按 azimuth 升序，同 azimuth 按 elevation 升序。

#### 缩略图

- 每个 view 生成一幅缩略图，写入 `diagnostics/thumbnails/{camera_id}.png`
- 宽 128px，高度等比例缩放
- 保持 RGBA（如果源图有 alpha 通道）

#### Contact sheet

- 所有缩略图的二维网格布局
- 按 view 顺序从左到右、从上到下排列
- 图片下方标注 `{azimuth}°/{elevation}°`
- 网格以 8 列为限（行数 = ceil(n_views / 8)）
- 背景白色，每条边距 4px，标题字体 10px
- 输出 `diagnostics/contact-sheet.png`

#### Completeness metrics

`diagnostics/completeness.json`：

```json
{
  "planned_views": 24,
  "available_views": 24,
  "completeness": 1.0,
  "azimuth_range_deg": [0, 315],
  "elevation_range_deg": [30, 90],
  "radius_m": 250.0,
  "missing_cameras": []
}
```

### 关键约束

1. **后端无关**：只读标准 v1 数据集，不含 Blender-specific 路径
2. **仅 PIL + json + 标准库**：与 Task 01/02 相同的依赖策略（缩略图缩放用 PIL 的 `Image.thumbnail`）
3. **确定性**：相同输入数据集产生完全相同的输出文件（包括 contact sheet 的像素级一致）
4. **稳定性**：不要求图像存在——missing_views 中列出缺失的 camera_id，而不是崩溃
5. **不多不少**：只报告 dataset 中实际存在的帧，不编造视图

### 与 Task 01 evaluation.py 的区别

Task 01 的 evaluation.py 有 ground-truth 对比（PSNR/MAE）。Task 03 **没有** ground truth，
因此不产生对比指标，只产生完整性统计。

## 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/tasks/drone_lookat_set/product_writer.py` | `write_viewset_product()`——主入口 |
| 新建 | `tests/test_drone_lookat_product.py` | 测试文件 |
| 修改 | `src/geglb/tasks/drone_lookat_set/__init__.py` | 导出 `write_viewset_product` |

### 禁止修改

- `src/geglb/products/viewset.py`
- `src/geglb/tasks/drone_lookat_set/{capture_plan,hemisphere,specification,workflows}.py`
- `src/geglb/core/*`
- `scripts/*`
- `schemas/*`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `src/geglb/tasks/underbody_image/evaluation.py` | **主参考**——产品写入模式、`produce_underbody_product()` 的流程（validate→compose→write diagnostics→write manifest） |
| `src/geglb/products/viewset.py` | `LookAtView`、`LookAtViewSetProduct` 的字段定义 |
| `src/geglb/tasks/drone_lookat_set/capture_plan.py` | `CaptureModel` 结构、`_entry()` 格式、entries 中的 camera_id 命名规则 |
| `src/geglb/core/dataset.py` | `validate_dataset()`、`read_jsonl()`、`write_json()` |
| `schemas/products/lookat-viewset.schema.json` | 产品 schema |

## 测试要求

`tests/test_drone_lookat_product.py`：

- [ ] `test_write_viewset_product_creates_all_artifacts`——viewset.json、thumbnails 目录、contact-sheet.png、completeness.json 全部存在
- [ ] `test_viewset_json_matches_schema`——输出的 viewset.json 通过 `LookAtViewSetProduct` 的 schema 验证
- [ ] `test_view_order_is_deterministic`——两次运行输出相同的 viewset.json
- [ ] `test_thumbnail_dimensions`——缩略图宽 128px，高度正确
- [ ] `test_contact_sheet_dimensions`——24 个视图（8列×3行）→ contact sheet 宽 > 0，行数正确
- [ ] `test_completeness_report`——有 24 个视图时 completeness=1.0；无图像时列出 missing_cameras
- [ ] `test_rejects_invalid_dataset`——数据集缺少关键文件时报错
- [ ] `test_graceful_handling_of_missing_images`——删掉一个图像文件后，completeness.json 中列出缺失

## 验收标准

- [ ] `python -m unittest tests.test_drone_lookat_product -v` 8/8 通过
- [ ] `ruff check src/geglb/tasks/drone_lookat_set/product_writer.py tests/test_drone_lookat_product.py` 零错误
- [ ] `ruff format --check` 已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 98/98 通过（原 90 + 新增 8）
- [ ] 零新依赖
- [ ] 不修改 core/、scripts/、products/、specification/hemisphere/capture_plan

## 设计提示

1. **从 frames.jsonl 恢复视图信息**：每个 frame 的 `camera_id` 包含 azimuth 和 elevation（`az{deg}_el{deg}`）。用 `int(frame["camera_id"].split("_")[0][2:])` 解析 azimuth，`int(frame["camera_id"].split("_")[1][2:])` 解析 elevation。
2. **缩略图生成**：使用 PIL 的 `Image.thumbnail((128, height))` 而不是 `resize()`，保持比例。遍历 `images/` 目录下的所有子目录。
3. **Contact sheet 合成**：用 PIL 的 `Image.new("RGB", (total_w, total_h), "white")` + `paste()`。标注用 `ImageDraw.Draw.text()` 加 `ImageFont.load_default()`。
4. **`missing_cameras` 检测**：比较 `frames.jsonl` 中 `status != "ground_truth_only"` 的帧与 `images/` 目录中的实际文件。
5. **radius 信息**：从 `rig.json` 的 `observer.radius_m` 字段读取。如果不存在（v1 兼容），设为 0。
