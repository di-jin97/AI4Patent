# IDEA 评审：原 Skill 与结构化 1.0 对比

## 结论

结构化 IDEA 评审 1.0 已成为默认入口：它实现原 `patent-IDEA-analyzer` 的 Step 0--6 用户功能，但将“模型一次性完成”替换为可恢复 workflow、渐进式 Skills、事实 ToolCall 与证据质量门。原 Skill 保留为 feature flag 回滚，不删除也不改写。

## 流程差异

| 维度 | 原始 Skill | 结构化 1.0 |
| --- | --- | --- |
| 编排 | 一个 OpenCode 会话加载约 1,100 行指令，工具结果与历史都累积在模型上下文 | SQLite Case State + 状态机 checkpoint；每步可取消、查询和恢复 |
| 语义处理 | 一个大 Skill 负责需求、检索、判断、报告 | 8 个子 Skill 分别处理需求、特征、检索规划、证据、创造性、商业、审查意见、报告组织；每次只收状态切片 JSON |
| 检索 | MCP/Exa 与模型工具调用耦合 | `GooglePatentsProvider` 独立 ToolCall：检索、书目信息、章节、段落匹配、关系；可再加 Provider/Adapter |
| 全文与证据 | 模型在会话中阅读/概述，证据一致性不可机器验证 | 全文记录、稳定 locator、内容 hash、EvidenceItem、日期校验和质量门 |
| 新颖性 | 模型按提示输出 | 单篇、全部必要特征、有效公开日、可定位证据的确定性矩阵；不满足时不输出否定新颖性 |
| 创造性 | 提示词要求 D1/D2 三步法 | 结构化 D1 路线、区别特征、D2、结合动机证据；缺结合动机时为 `uncertain` |
| 报告 | 通常只在聊天输出，Word/Excel 为模型工具的可选动作 | 固定八章 Markdown、冻结 State JSON；按请求生成 DOCX/XLSX，渲染不再检索 |

## Step 0--6 映射

| 原 Step | 1.0 实现 |
| --- | --- |
| 0 需求理解 | `patent-idea-intake` → `state.invention` |
| 1 特征/权利要求/检索词 | `patent-feature-parser`、`patent-search-planner` → Feature、Claim、Query、SearchPlan |
| 2 检索与全文 | Google ToolCalls → 去重、排序、全文记录与章节定位 |
| 3 新颖性 | Evidence extraction → `evaluate_novelty()` → Quality Gate |
| 4 创造性与价值 | `patent-inventiveness`、`patent-commercial-value` + 结构化路线/置信度 |
| 5 审查意见 | `patent-examiner-opinion`，只引用已完成的状态与质量门 |
| 6 报告 | `patent-report-renderer` + 确定性 MD/JSON/DOCX/XLSX Renderer |

## 运行与回滚

默认：IDEA 页面选择结构化 1.0。直接 Google 访问需在确认来源政策后显式设定 `GOOGLE_PATENTS_DIRECT_ACCESS_ENABLED=true`；ToolCall 会检查 robots、限速和缓存，不能访问时返回可解释失败而非空结论。

立即回滚：启动前设置 `IDEA_STRUCTURED_BETA_ENABLED=false`，页面隐藏结构化选项并继续调用原 `patent-IDEA-analyzer`。

## 已验证范围与仍需人工复核

- 自动化：Provider HTML/JSON fixture、Skill 契约、完整 D1/D2 离线案件、Case API/SSE、DOCX/XLSX、Golden cases 与前端默认入口，共 131 项测试。
- 线上冒烟：Google Patents 搜索成功返回真实公开号 `EP3210121B1`；其公开详情页也成功返回可定位权利要求章节。
- 仍需发布门槛：PRD 要求的 20 个真实代表性案例与人工双跑抽样尚未完成，因此结果应作为检索辅助和模拟审查意见，不构成法律意见。
