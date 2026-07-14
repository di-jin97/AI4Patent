# IDEA 评审：原始完整 Skill 与当前结构化版本对比

**状态：2026-07-14，基于提交 `744b5ab`。**

本文比较的对象是：

- **原始版本（Legacy）**：`config/opencode/skills/patent-IDEA-analyzer/SKILL.md`，一个约 1,100 行的完整 Skill。
- **当前版本（Structured Beta）**：`backend/patent_analysis/`、Case API 与 IDEA 页面中的“结构化 Beta”入口。

结论先行：**当前版本不是原始完整 Skill 的等价替代品。**它已经把案件状态、检索服务、文献、证据和质量约束拆到可测试的代码中，并已挂载成可运行的 Beta；但原 Skill 中“全量全文取证、D1/D2 多路线创造性推导、价值预评估、模拟审查意见、完整八章报告”等业务行为尚未完全迁移。因此，默认入口仍应使用原 Skill，Beta 用于验证新的结构化执行底座。

## 1. 两条实际运行路径

```text
Legacy（默认）
IDEA 页面 → /api/run → opencode run → patent-IDEA-analyzer Skill
                                      ↓
                         模型在一次上下文中执行 Step 0–6

Structured Beta（显式启用）
IDEA 页面 → /api/cases → SQLite Case State → WorkflowOrchestrator
                                                  ↓
                              SearchProvider → Exa 远程 MCP
                                                  ↓
                         SSE 进度 + 状态检查点 + Markdown Artifact
```

结构化 Beta 只有在服务启动前设置 `IDEA_STRUCTURED_BETA_ENABLED=true` 时才会在 IDEA 页面显示。关闭该环境变量即可立即回退 Legacy；`/api/run` 没有被删除或改写。

## 2. 核心差异

| 维度 | 原始完整 Skill | 当前结构化 Beta | 当前判断 |
| --- | --- | --- | --- |
| 编排位置 | 长 Prompt 内的 Step 0–6，靠模型上下文维持进度 | `WorkflowOrchestrator`、状态机与 SQLite checkpoint | Beta 已具备可恢复的执行骨架 |
| 案件状态 | OpenCode session 和流式文本，不是业务案件状态 | `PatentCaseState` 含 case、feature、document、evidence、结论、trace、artifact | 已迁移 |
| IDEA 解析 | 模型提炼 A–F 技术特征、归一化权利要求 | 当前按语句分割为保守特征列表 | **部分迁移；不是等价的权利要求解析器** |
| 检索规划 | 两批检索式、中文/英文、分类号和区别特征追加检索 | 当前生成一条基线特征查询 | **部分迁移** |
| Exa 调用 | OpenCode 为模型提供 `exa_web_search_exa` / `exa_web_fetch_exa` | `SearchProvider` → `ExaAdapter` → Streamable HTTP MCP | 已解耦；工具名与 OpenCode 前缀差异已修复 |
| 可替换检索服务 | 搜索规则散落在 Skill/全局提示中 | `SearchProvider` 接口；可新增 Provider 后在 `backend/main.py` 注入 | 架构已支持 |
| 结果去重与排序 | 模型按提示整理 | Python 代码规范化 URL/专利号、去重和排序 | 已迁移 |
| 全文抓取 | Step 2 要求对相关文献抓全文 | Beta 明确记录 `fulltext_deferred` | **未迁移到默认 Beta** |
| 可定位证据 | Skill 要求章节、专利号、链接等，主要由模型组织 | `EvidenceItem`、日期/定位/覆盖校验与 Quality Gate 已实现 | 数据契约已实现；自动提取未接入 Beta |
| 新颖性 | 单篇、全部必要特征、日期有效的逐篇比对 | `evaluate_novelty()` 可执行同一规则；Beta 无全文证据时固定为 `uncertain` | 引擎已实现，端到端证据输入未完成 |
| 创造性 | 至少三条 D1 路线、D2、结合动机、三步法 | 结构化模型已有 `InventiveStepResult` / route 字段；Beta 固定为 `uncertain` | **未迁移** |
| 商业/运营价值 | 可取证性、可规避性、市场/成熟度预评估 | 结构化模型已有容器；Beta 置信度为 0 | **未迁移** |
| 模拟审查意见 | Step 5 按最强攻击路线生成 | Beta 不生成 | **未迁移** |
| 报告 | 默认对话完整报告；追问时 Word/Excel | 从 State 生成安全的 Markdown Beta 报告 | Markdown 基线已实现；完整八章、DOCX/XLSX 未迁移 |
| 中断、恢复、取消 | 只能停止 OpenCode 进程或依赖 session 追问 | Case API、SSE、checkpoint、cancel/resume | 已挂载；复杂步骤的细粒度恢复仍待完善 |
| 测试方式 | 主要依赖一次实际模型执行 | 单元、Golden、Provider 契约、Case API、IDEA 端到端离线测试 | 显著增强 |
| 密钥/日志 | 配置与工具事件可能在调试输出中扩散 | secret 文件原子写入、权限收紧、递归日志脱敏 | 已加固；已暴露密钥仍须人工轮换 |

## 3. 原 Skill 的“全部操作”与 Beta 的逐步映射

原 Skill 会在一次模型会话中声称完成以下流程：

1. **Step 0–1**：理解用户需求、判断领域、提取完整技术特征、推断独立权利要求并构造两批检索式。
2. **Step 2**：多轮中英文检索、候选文献评级、全文抓取、来源和权利人校验、文件分流。
3. **Step 3**：以单篇文献和全部必要特征为条件做逐篇新颖性矩阵。
4. **Step 4**：选择至少三篇 D1，寻找 D2，按三步法完成多路线创造性分析，并给出运营价值预评估。
5. **Step 5–6**：输出模拟审查意见、完整对话报告；按需生成 Word/Excel。

当前 Beta 实际执行的是：

1. 创建案件、持久化输入；将 Idea 以确定性规则切成基线特征。
2. 创建一条基线查询，经真实 Exa MCP 检索候选文献，随后去重和排序。
3. 将每个状态转换写入 SQLite checkpoint，并经 SSE 推送步骤进度。
4. **显式跳过全文抓取和自动证据抽取**，不把摘要误认为法律证据。
5. 将新颖性、创造性设为 `uncertain`，运行 Quality Gate，生成 Markdown Beta 报告。

因此，Beta 的价值不是“更快地得出同样的专利结论”，而是先保证每一步的输入、输出、失败和恢复都可审计。完整业务逻辑必须在有经验证据的前提下逐步接入，不能用模型摘要补齐缺口。

## 4. 已验证能力与验证边界

已验证：

- 全量自动测试 `124 passed`。
- ExaAdapter 经真实远程 MCP 单结果检索，能返回并解析候选 URL。
- 使用一个随机生成的固态存储热数据迁移创新点，真实 Exa 端到端运行完成：`COMPLETED`、14 次状态修订、2 项基线特征、20 篇候选文献、Markdown artifact 已生成、Quality Gate 通过。
- 上述端到端案例的新颖性结论为 `uncertain`，符合“无可定位全文证据不作强结论”的约束。

未验证或尚未具备：

- Beta 尚未证明能产出与 Legacy 等质量的完整八章报告。
- Beta 尚未做真实全文抓取、权利要求/段落定位、D1/D2 路线或商业价值结论。
- 原 Skill 的真实模型端到端输出仍受模型、网络、MCP 服务和上下文质量影响；离线测试不能替代人工法律审阅。

## 5. 何时使用哪一个版本

| 使用目标 | 建议入口 | 原因 |
| --- | --- | --- |
| 现在就需要完整的模拟审查、创造性三步法、价值建议或按需 Word/Excel | Legacy（默认） | 这些规则目前仍集中在原 Skill 中 |
| 验证案件创建、状态推进、真实 Exa 搜索、日志和恢复机制 | Structured Beta | 结果可检查、可重试、可下载 Markdown artifact |
| 开发新的检索服务或证据处理器 | Structured Beta + FakeSearchProvider 测试 | 不必把 Provider 差异写回 Prompt |
| 需要严谨的授权风险结论 | 两者均需人工复核 | 系统不替代专业检索、代理师或律师意见 |

## 6. 从 Beta 走向等价替代的剩余工作

以下工作完成前，不能将 Structured Beta 设为默认：

1. **P1-01**：实现 D1/D2、结合动机、三步法创造性与商业价值引擎，并以 Golden case 对比原规则。
2. **P1-02**：将原 Skill 拆成渐进式入口与 references，保留原 Skill 作回滚基线。
3. **P1-03**：以冻结 State 渲染可重复的 Chat/Markdown/JSON，再补 DOCX/XLSX。
4. **全文与证据接入**：将真实 fetch、权利要求/段落定位、日期验证和 `EvidenceItem` 自动提取接到 Beta；不通过 Quality Gate 时禁止强结论。
5. **P2 双跑与人工抽样**：同一代表性案件同时运行两条路径，比对文献、证据、结论、预算和报告质量；满足门槛后才切换默认值。

## 7. 维护入口与回滚

| 事项 | 编辑位置 |
| --- | --- |
| 保持/修改原完整业务规则 | `config/opencode/skills/patent-IDEA-analyzer/SKILL.md` |
| Beta 工作流步骤 | `backend/patent_analysis/steps.py` |
| Case API、SSE、取消与恢复 | `backend/patent_analysis/api.py` |
| State、证据和结论契约 | `backend/patent_analysis/domain/models.py` |
| 更换搜索服务 | 新建 `SearchProvider` 实现，并在 `backend/main.py` 注入 |
| Legacy Exa MCP | `config/opencode/opencode.json` 的 `mcp.exa` |
| Beta Exa 地址/可选 key | `EXA_MCP_URL` / `EXA_API_KEY` 环境变量 |
| 启用/关闭 Beta | `IDEA_STRUCTURED_BETA_ENABLED=true`；未设置即 Legacy |

回滚不需要迁移数据：关闭 `IDEA_STRUCTURED_BETA_ENABLED` 即可隐藏 Beta UI 并继续走 `/api/run`。不得删除原 `patent-IDEA-analyzer`，直到双跑、质量、隐私和人工抽样全部通过。
