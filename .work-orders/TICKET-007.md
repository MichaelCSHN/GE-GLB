---
id: TICKET-007
title: "产品验证框架 — validate-product CLI + 质量指标"
status: active
assignee: "DeepSeek"
created: 2026-07-18
depends_on: [TICKET-001, TICKET-002, TICKET-003, TICKET-006]
estimated_hours: 4-6
---

## 背景

当前三个 Task 的产品管线已完整，但缺少统一的**产品验证**手段：

| Task | 产品写入器 | 产品 schema | 验证方式 | 
|------|-----------|------------|---------|
| 01 | `evaluation.py` | `underbody-image.schema.json` | 仅 test 中用 jsonschema 验证 |
| 02 | `compositor.py` | `panorama-360.schema.json` | 仅 test 中用 jsonschema 验证 |
| 03 | `product_writer.py` | `lookat-viewset.schema.json` | 仅 test 中用 jsonschema 验证 |

三个产品的验证代码分散在测试中，没有一个命令行工具可以这样用：

```powershell
geglb validate-product build/task01/product --type underbody
```

PLAN.md 中对应的条目：
> `[ ] Add one-panorama product validator and quality metrics.`

本工单要求实现一个**跨产品的统一验证框架**，支持 CLI 调用，输出结构化验证报告。

## 要求

### 第一部分：核心验证模块

新建 `src/geglb/products/validate.py`，包含以下函数：

#### `validate_product(product_dir: str | Path, product_type: str) -> dict[str, object]`

验证逻辑：

1. 根据 `product_type` 加载对应的 JSON Schema（从 `schemas/products/` 读取）
2. 读取 `product/manifest.json`
3. 用 `jsonschema` 验证 manifest 与 schema 匹配
4. 检查 `primary_artifact` 是否存在且可解码（`underbody.png` / `panorama.png` / `viewset.json`）
5. 按 product_type 检查特有字段：

| type | 特有检查 |
|------|---------|
| `underbody` | `diagnostics/confidence.png` 存在、`diagnostics/coverage.png` 存在、`ground_truth_metrics` 可选 |
| `panorama` | `diagnostics/validity.png` 存在、`diagnostics/coverage.png` 存在、image 尺寸 2:1 比例 |
| `lookat` | `diagnostics/completeness.json` 可解析、`diagnostics/thumbnails/` 目录存在、viewset.json 中 views 数组非空 |

6. 报告覆盖率/完整性统计数据
7. 收集警告（如缺失诊断、低覆盖率）

**函数签名：**

```python
def validate_product(
    product_dir: str | Path,
    product_type: str,
) -> dict[str, object]:
    """Validate a product directory against its schema and quality criteria.

    Returns a structured report:
    {
        "valid": bool,
        "product_type": str,
        "product_schema": str,
        "errors": [str, ...],
        "warnings": [str, ...],
        "primary_artifact": str,
        "primary_artifact_ok": bool,
        "diagnostics": {"name": bool, ...},
        "quality": {"coverage": float, ...},
    }
    """
```

### 第二部分：CLI 入口

在 `cli/main.py` 中添加：

```python
validate_product = commands.add_parser("validate-product", help="Validate a product directory")
validate_product.add_argument("product_dir")
validate_product.add_argument("--type", required=True, choices=["underbody", "panorama", "lookat"])
```

命令调用 `products.validate.validate_product()` 并打印结果。验证失败（`valid=False`）返回 exit code 2。

### 第三部分：补充 metadata

每个产品写入器需要在产物 manifest 中补充一个 `"geglb_version"` 字段，值为 `geglb.__version__`：

| 文件 | 所在函数 |
|------|---------|
| `tasks/underbody_image/evaluation.py` | `produce_underbody_product()` |
| `tasks/roof_360_pano/compositor.py` | `build_panorama()` |
| `tasks/drone_lookat_set/product_writer.py` | `write_viewset_product()` |

### 第四部分：产品类型注册表

在 `products/validate.py` 中维护一个验证项注册表，而非硬编码 if/else：

```python
PRODUCT_VALIDATORS: dict[str, ProductValidator] = {
    "underbody": ProductValidator(...),
    "panorama": ProductValidator(...),
    "lookat": ProductValidator(...),
}
```

其中 `ProductValidator` 是一个包含 schema_path、required_diagnostics、custom_check 的 dataclass。

## 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `src/geglb/products/validate.py` | 核心验证框架 + ProductValidator 注册表 |
| 修改 | `src/geglb/cli/main.py` | 添加 `validate-product` 子命令 |
| 修改 | `src/geglb/tasks/underbody_image/evaluation.py` | 添加 `geglb_version` 到 manifest |
| 修改 | `src/geglb/tasks/roof_360_pano/compositor.py` | 添加 `geglb_version` 到 manifest |
| 修改 | `src/geglb/tasks/drone_lookat_set/product_writer.py` | 添加 `geglb_version` 到 manifest |
| 新建 | `tests/test_product_validate.py` | 测试文件 |

### 禁止修改

- `src/geglb/products/base.py`
- `src/geglb/products/{image,panorama,viewset}.py`
- `src/geglb/core/*`
- `schemas/*`
- `tests/test_architecture.py`（已有 schema 解析测试）

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `schemas/products/underbody-image.schema.json` | 每个 product type 的 schema 格式 |
| `schemas/products/panorama-360.schema.json` | |
| `schemas/products/lookat-viewset.schema.json` | |
| `tests/test_schemas.py` | 现有测试中如何用 Draft202012Validator 验证 |
| `src/geglb/core/dataset.py` 的 `validate_dataset()` | 现有 dataset 验证器的输出结构和错误处理模式 |
| `src/geglb/cli/main.py` 的 `validate` 子命令 | CLI 中验证命令的模式（exit code 2） |

## 测试要求

`tests/test_product_validate.py`：

- [ ] `test_validate_valid_underbody_product`——先用 `produce_underbody_product()` 生成合法产品，再验证，返回 valid=True
- [ ] `test_validate_valid_panorama_product`——同上，对 panorama
- [ ] `test_validate_valid_lookat_product`——同上，对 lookat
- [ ] `test_validate_missing_manifest`——产品目录无 manifest.json，valid=False
- [ ] `test_validate_wrong_type`——传入不匹配的 product_type，valid=False
- [ ] `test_validate_degraded_image`——primary_artifact 文件损坏，valid=False 或 warnings 非空
- [ ] `test_validate_missing_diagnostics`——删除一张诊断图，warnings 非空
- [ ] `test_cli_validate_product`——实际子进程调用 `geglb validate-product`，验证输出

## 验收标准

- [ ] `python -m unittest tests.test_product_validate -v` 8/8 通过
- [ ] `ruff check src/geglb/products/validate.py src/geglb/cli/main.py tests/test_product_validate.py` 零错误
- [ ] `ruff format --check` 已格式化
- [ ] `python -m compileall -q src tests` 零错误
- [ ] `python -m unittest discover -s tests -v` 106/106 通过（原 98 + 新增 8）
- [ ] 零新依赖（`jsonschema` 已在 `dev` 依赖中）
- [ ] 不修改 core/、schemas/

## 设计提示

1. **product_type → schema 映射**：schema 文件位置可以从 product type 推断：`underbody` → `products/underbody-image.schema.json`，`panorama` → `products/panorama-360.schema.json`，`lookat` → `products/lookat-viewset.schema.json`
2. **延迟导入 jsonschema**：只在 `validate_product()` 被调用时才 import，不在模块顶层 import（因为它是 dev 依赖，不是核心依赖）
3. **Primary artifact 验证**：对图像文件（underbody.png、panorama.png）用 PIL 尝试 open；对 JSON 文件（viewset.json）用 json.load 尝试解析。捕获并记录异常作为 error
4. **test_cli_validate_product** 参考现有 test 模式，用 `subprocess.run` 或直接调用 `main()` 函数
