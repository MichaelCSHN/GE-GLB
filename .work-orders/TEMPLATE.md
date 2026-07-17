---
id: TICKET-NNN
title: "<简短标题>"
status: draft | active | review | closed
assignee: "<谁>"
created: <YYYY-MM-DD>
depends_on: []
---

## 背景

<!-- 为什么要做、上下文 -->

## 要求

<!-- 输入、输出、关键约束 -->

## 文件清单

| 操作 | 路径 | 说明 |
|------|------|------|
| 新建 | `path/to/new.py` | ... |
| 修改 | `path/to/existing.py` | ... |

### 禁止修改

- `path/to/forbidden.py`

## 参考代码（必须阅读）

| 文件 | 看点 |
|------|------|
| `path/to/ref.py` | ... |

## 测试要求

- [ ] test_xxx

## 验收标准

- [ ] 测试 N/N 通过
- [ ] ruff lint/format clean
- [ ] compileall 零错误
- [ ] 全量测试回归通过
- [ ] 零新依赖
