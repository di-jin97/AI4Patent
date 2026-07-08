# Patent PCT Review

评审一批专利是否需要进入 PCT 阶段，通过五个维度打分排序，辅助决策。

---

## 是什么

上传一份 Excel（含专利清单）和对应的 DOCX 申请文件，AI 逐个读取申请文件，从市场价值、创新性、取证便利性、抗规避性、落地程度五个维度打分（1-5 分），按总分排序后取前约 40% 建议进入 PCT，输出填报结果的 Excel 副本。

---

## 文件结构

```
patent-pct-review/
├── README.md                 # 本文件
├── SKILL.md                  # 主流程（Phase 0-4）
└── scripts/
    ├── extract_key_sections.py  # 从专利全文抽取关键段
    └── score_and_decide.py      # 排序 + 决策
```

| 文件 | 职责 |
|------|------|
| SKILL.md | 评审流程编排，控制循环逻辑 |
| scripts/extract_key_sections.py | 从 DOCX 中抽取权利要求、技术方案、背景技术、有益效果（≤2000字） |
| scripts/score_and_decide.py | 按总分排序并决策前 40% 进 PCT |

---

## 使用方式

提供 Excel 和 DOCX 申请文件后，触发示例：

- "帮我评审这批专利要不要进 PCT"
- "做海外专利评审"
- "判断哪些专利值得申请 PCT"

输入要求：
- **Excel**：含 Priority sheet，专利号在 Patent Ref 列
- **DOCX**：与 Excel 同目录，AI 按专利号前 8 位数字自动匹配文件

---

## 输出说明

输出原 Excel 的副本，新增六列：

| 列名 | 说明 |
|------|------|
| 发明概述 | 解决什么问题 + 用什么方案 + 创新点（≤200字） |
| 市场价值 | 适用场景/产品 + 落地情况（≤100字） |
| 创新性 | 相对检索到的现有技术的创新程度（≤100字） |
| 取证手段 | 取证方式 + 难度（≤100字） |
| 可规避性 | 难规避/中等/易规避（≤100字） |
| Paris Convention Deployment Suggestion | 进 PCT / 不进 PCT |

进入 PCT 比例约 40%，按总分降序排列。

---

## 依赖

| 依赖 | 用途 |
|------|------|
| Python 3.x | 运行脚本 |
| openpyxl | 读写 Excel |
| python-docx | 读取 DOCX 申请文件 |
| exa_web_search_exa | 检索现有技术（不可用时基于自身知识分析） |
| scripts/extract_key_sections.py | 抽取专利关键段 |
| scripts/score_and_decide.py | 排序并决策 |

---

## 注意事项

- 分析基于 AI 对说明书的独立判断，不应被申请文件的夸张语言影响评分
- 每次分析一个专利，读一个 → 评一个 → 落盘 → 读下一个，不会批量读完再评
- 进入 PCT 数量必须大于 0，比例控制在 35%-45%
- 每件专利在分析前会检索 2-3 篇相关现有技术辅助判断创新性