# Patent IDEA Review 1.0 产品需求文档（PRD）

| 项目 | 内容 |
| --- | --- |
| 状态 | 已批准实施基线 |
| 产品目标 | 以渐进式 Skill、可审计 workflow 和自有专利数据 ToolCall 完整替代原始 IDEA Skill 的用户功能 |
| Legacy 基线 | `config/opencode/skills/patent-IDEA-analyzer/SKILL.md` |
| 目标入口 | IDEA 页面默认使用 `Case API → workflow → progressive skills`；Legacy 可通过 feature flag 回滚 |

## 1. 问题与目标

原始 Skill 能一次性给出完整审查意见，但所有中间事实、检索结果和推理都存在模型会话中。用户无法恢复中断任务，系统也不能验证“结论是否有原文和日期依据”。当前 Structured Beta 已有案件与状态基础，但尚不能完成原 Skill 的完整业务。

本版本的目标不是缩减功能，而是在保持原 Skill Step 0–6 功能的同时，实现：

1. 每个确定结论可追溯到文献、定位原文、日期和 State revision。
2. 检索数据通过自有 ToolCall 获取，不依赖 Exa MCP；Google Patents 是第一 Provider。
3. Skill 按步骤渐进加载，模型每次只接收完成当前任务必需的 State 和证据片段。
4. 工作流可取消、恢复、重试、限额、双跑和回滚。
5. 新旧输出可比较；新实现通过验收前，Legacy 保留且默认可回退。

## 2. 用户与使用场景

| 用户 | 场景 | 成功标准 |
| --- | --- | --- |
| 发明人 | 输入方案，快速判断是否值得继续申请 | 获得带来源的风险、区别特征和下一步建议 |
| 专利工程师 | 标准审查与复核 | 可查看每个结论对应的权利要求/段落、公开日和检索式 |
| 分析负责人 | 深度检索、D1/D2 三步法与报告 | 可恢复长任务，导出 Markdown/JSON/DOCX/XLSX，保留审计轨迹 |
| 维护者 | 更换数据源或模型 | 新 Provider/Skill 不修改评估规则和工作流状态机 |

## 3. 功能需求

### FR-01 案件与模式

- 创建 Case 时冻结 Idea、优先权日、法域、运行模式和配置版本。
- 支持 `quick`、`standard`、`deep`、`commercial` 模式，模式只改变预算与输出深度，不改变证据标准。
- 支持状态查询、SSE 进度、取消、恢复和产物下载。

### FR-02 渐进式语义 Skills

系统必须提供以下子 Skill，并使用 JSON Schema 作为唯一输入输出契约：

1. `patent-idea-intake`：Step 0 需求理解、审查范围、法域、日期和不确定项。
2. `patent-feature-parser`：Step 1 技术特征、归一化独立权利要求、同义词和技术领域。
3. `patent-search-planner`：两批检索式、语言、CPC/IPC、查询目的和预算。
4. `patent-evidence-extractor`：从已抓取全文提取带 claim/段落定位的特征证据。
5. `patent-inventiveness`：D1/D2、区别特征、实际技术问题、结合动机和三步法路线。
6. `patent-commercial-value`：可取证性、可规避性、市场、成熟度和置信度。
7. `patent-examiner-opinion`：基于通过质量门的最强路线生成模拟审查意见。
8. `patent-report-renderer`：从冻结 State 生成对话、MD、JSON、DOCX、XLSX。

禁止子 Skill 依赖“记住前面聊天内容”；它们只能读取 workflow 传入的 State 切片和 artifact 引用。

### FR-03 自有专利数据 ToolCall

第一 Provider 为 Google Patents，必须提供下列独立调用：

| ToolCall | 必须输出 |
| --- | --- |
| `patent_search` | 候选列表、查询回显、分页、来源 URL、检索时间 |
| `patent_get_biblio` | 公开号、题名、申请/公开/优先权日、申请人、发明人、IPC/CPC、来源字段 |
| `patent_get_sections` | 摘要、指定 claim、说明书片段；每段含稳定 locator 和 content hash |
| `patent_find_passages` | 已抓取文本中与特征匹配的候选 claim/段落，供 Evidence Skill 审核 |
| `patent_get_relations` | 可选的同族、引证、被引证关系；来源缺失时必须标注 |

ToolCall 只返回事实和定位，不做新颖性、创造性或商业判断。

Google 页面访问必须服从 robots/条款、限速、缓存和显式开关；不得绕过反自动化措施。大规模发现与统计由可选 BigQuery Provider 承担。

### FR-04 原 Skill Step 0–6 功能对等

| 原 Step | 新流程验收 |
| --- | --- |
| Step 0 | 需求范围、技术领域、限定条件、深度与不确定项结构化保存 |
| Step 1 | A–F 特征、归一化权利要求、双语/分类号检索词和两批查询计划 |
| Step 2 | 多轮检索、结果去重/评级、数据来源验证、全文抓取、D1/D2 分流 |
| Step 3 | 单篇文献、必要特征全覆盖、日期有效、可定位证据的新颖性矩阵 |
| Step 4 | 至少按模式要求的 D1 路线、D2、结合动机、三步法和价值评估 |
| Step 5 | 以最强通过质量门的路线生成模拟审查意见 |
| Step 6 | 八章完整报告；Chat/MD/JSON 必须有，DOCX/XLSX 按请求生成 |

### FR-05 证据与质量门

- “不具备新颖性”必须由单一公开日有效文献覆盖所有必要特征，且每个特征至少有一个可定位 EvidenceItem。
- “不具备创造性”必须指向 D1、区别特征、D2/常识、结合动机及其证据。
- 证据不足时输出 `uncertain` 或 `partial`，但报告要列出缺口与下一步检索动作。
- 不得将搜索摘要、模型猜测的段落号或未验证日期作为确定结论证据。

### FR-06 输出与审计

- 默认输出完整八章 Markdown；同时保存 JSON State artifact。
- 每个 artifact 记录 State revision、模板版本、内容 hash 和生成时间。
- DOCX/XLSX 只在请求时生成；任何渲染器不得重新检索或修改事实。
- UI 可展开“结论 → 路线 → 文献 → 原文定位”的证据链。

## 4. 非功能需求

| 主题 | 要求 |
| --- | --- |
| 可恢复 | 每个外部请求和语义 Skill 步骤必须 checkpoint、幂等或可安全重试 |
| 成本 | 模式配置最大搜索、抓取、token、耗时和 D1/D2 数量 |
| 安全 | Idea、密钥和 ToolCall 头部不得进入普通日志；原文 artifact 私有存储 |
| 可测试 | Provider fixture、Skill JSON fixture、Golden case、API/SSE、双跑对比必须自动化 |
| 可替换 | Workflow 仅依赖 `PatentDataProvider`、`SkillRunner`、Renderer 契约 |
| 合规 | 来源条款、robots、速率和授权状态必须可配置和可审计 |

## 5. 发布与替换门槛

新入口可以替换默认值，必须同时满足：

1. 每个 Step 0–6 都有映射实现和测试，而非仅有 State 字段。
2. 至少 20 个代表性案例完成 Legacy/New 双跑；文献、证据、结论和报告章节由人工抽样复核。
3. Golden、Provider、Skill、API、Renderer 测试全绿；真实 Provider 失败有可解释降级。
4. 默认输出不再出现“因为功能未实现而固定 uncertain”；`uncertain` 只能由真实证据不足触发。
5. feature flag 可以立即回滚到 Legacy。

## 6. 非目标

- 不把系统表述为正式法律意见或保证穷尽性。
- 不绕过 Google 或其他来源的访问限制。
- 不在第一版引入分布式队列、Kafka 或微服务；保持模块化单体。
