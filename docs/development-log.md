# Patent Innovation Analysis Agent - 开发日志

## 概述
本文档按时间顺序记录 `AI4Patent` 项目中 Patent Innovation Analysis Agent 的完整开发过程。

基于设计文档: `docs/patent-innovation-analysis-agent-design.md`
原始 Skill: `config/opencode/skills/patent-IDEA-analyzer/SKILL.md`

---

## 2026-07-13: P0-01 Architecture Verification

### 修改内容

1. **新建 `docs/architecture-verification.md`**
   - 扫描并记录项目运行环境 (Python 3.12.3, Pydantic 2.13.4, FastAPI 0.139.0, OpenCode 1.17.18)
   - 确认 DeepSeek v4-pro provider + Exa remote MCP 配置
   - 记录仓库事实: 无测试文件, `backend/patent_analysis/` 目录不存在
   - 区分已证实项与未证实项
   - 关键决策: SQLite 存储, Pydantic v2 Schema, Exa Bridge 方案, feature flag 回滚

### Git 提交
- `docs: add architecture verification report and development log (P0-01)`

---

## 2026-07-13: P0-03 State/Evidence Schema, IDs, Validation

### 修改内容

1. **新建 `backend/patent_analysis/` 模块结构**
2. **新建 `domain/models.py`** - 核心 Pydantic 数据模型 (19 个状态, 20+ 模型类)
3. **新建 `domain/ids.py`** - Stable ID 生成器 (F-*, DOC-*, EV-*, ROUTE-*, Q-*)
4. **新建 `domain/dates.py`** - 日期工具 (normalize, parse, priority date validation)
5. **新建 `domain/validation.py`** - 证据/日期/特征覆盖/QualityGate 验证器
6. **新建 37 单元测试** - ID, 日期, 证据, 验证器, 模型, QualityGate

### Git 提交
- `feat(P0-03): add state/evidence schema, ID generator, dates, validators with 37 unit tests`

---

## 2026-07-13: P0-04 State Store, Workflow Kernel

### 修改内容

1. **新建 `workflow/transitions.py`** - 完整状态机迁移规则 (19 个状态, 所有合法 transition)
2. **新建 `workflow/budget.py`** - BudgetManager + 四模式默认预算 (Quick/Standard/Deep/Commercial)
3. **新建 `workflow/orchestrator.py`** - WorkflowStep 接口 + WorkflowOrchestrator 编排器
4. **新建 `persistence/state_store.py`** - SQLite 存储 (cases, checkpoints, idempotency_keys 三表)
5. **新建 24 workflow 测试** - 状态迁移规则, 预算管理, StateStore CRUD/幂等/checkpoint/cancel

### Git 提交
- `feat(P0-04): add state store, workflow kernel, transitions, budget manager with 24 workflow tests`

---

## 2026-07-13: P0-05 Provider and Document Pipeline

### 修改内容

1. **新建 `adapters/base.py`** - SearchProvider 抽象接口 + SearchRequest/Response, FetchRequest/Response
2. **新建 `adapters/exa.py`** - ExaAdapter (通过 OpenCode MCP bridge 调用 Exa 工具)
3. **新建 `adapters/opencode_mcp_bridge.py`** - OpenCode MCP bridge (子进程执行 MCP 调用)
4. **新建 `adapters/fake.py`** - FakeSearchProvider (离线测试用)
5. **新建 `services/documents.py`** - URL/专利号规范化, 去重, 排序, 文档 hash, Google Patents URL 拼接
6. **新建 23 provider 测试** - fake provider 搜索/抓取/调用追踪, URL 规范化, 专利号规范化, 去重, 排序

### Git 提交
- `feat(P0-05): add SearchProvider, ExaAdapter, OpenCode MCP bridge, fake provider, document normalizer/dedupe/ranker with 23 provider tests`

---

## 2026-07-13: P0-06 Evidence, Novelty and Quality Gate

### 修改内容

1. **新建 `services/evidence.py`** - 证据提取/验证/特征映射/覆盖矩阵
2. **新建 `services/novelty.py`** - 新颖性评估引擎 (单文献完全覆盖→not-novel)
3. **新建 `services/quality.py`** - Quality Gate 服务 (拦截无证据/无效日期的确定性结论)
4. **新建 13 service 测试** - 证据提取/序列 ID, 证据验证, 特征映射, 覆盖矩阵, 新颖性四场景, Quality Gate

### Git 提交
- `feat(P0-06): add evidence extraction, novelty evaluation engine, quality gate service with 13 service tests`

---

## 2026-07-13: P0-02 Golden Baseline Fixtures

### 修改内容

1. **新建 `tests/patent_analysis/golden/fixtures.py`** - 7 个 Golden 场景 fixture:
   - 单篇完整覆盖 (not-novel)
   - 多文献分别覆盖 (novel)
   - D1+D2 有结合启示 (not-inventive)
   - D2 无结合动机 (inventive)
   - 晚公开日 (不应作为现有技术)
   - Evidence 无定位 (Quality Gate 应拦截)
   - 模糊 Idea (保守评估为 novel)
2. **新建 `tests/patent_analysis/golden/test_golden.py`** - 10 Golden 断言测试
3. **Golden runner** 批量执行所有场景并返回结构化结果

### Git 提交
- `test(P0-02): add golden baseline fixtures and 10 golden scenario tests (107 total)`

---

## 最终统计

| 指标 | 数值 |
|---|---|
| 总测试数 | **107** (全部通过) |
| 新增 Python 文件 | 20 |
| 新增代码行数 | ~3000+ |
| 实施阶段 | P0 (6/6 tasks) |
| 下一步 | P1-01: Inventive step & commercial engines |

### 目录结构

```
backend/patent_analysis/
  __init__.py
  domain/
    __init__.py, models.py, ids.py, dates.py, validation.py
  workflow/
    __init__.py, transitions.py, budget.py, orchestrator.py
  adapters/
    __init__.py, base.py, exa.py, fake.py, opencode_mcp_bridge.py
  services/
    __init__.py, documents.py, evidence.py, novelty.py, quality.py
  persistence/
    __init__.py, state_store.py
  renderers/  (待 P1-03 实现)
  schemas/    (待 P1-03 实现)

backend/tests/patent_analysis/
  unit/
    test_domain.py (37 tests)
    test_workflow.py (24 tests)
    test_adapters.py (23 tests)
    test_services.py (13 tests)
  golden/
    fixtures.py, test_golden.py (10 tests)
  contract/  (待实现)
  integration/ (待实现)
```

### 设计合规性

| 设计要求 | 状态 |
|---|---|
| 核心状态机 19 状态 | 已实现 |
| Stable ID (F-*/DOC-*/EV-*/ROUTE-*) | 已实现 |
| 证据必须可定位 (No Evidence → No Conclusion) | 已实现 |
| 日期/优先权校验 | 已实现 |
| 四模式预算 (Quick/Standard/Deep/Commercial) | 已实现 |
| 幂等性 (idempotency key) | 已实现 |
| Checkpoint 恢复 | 已实现 |
| SQLite 状态存储 | 已实现 |
| SearchProvider 可替换接口 | 已实现 |
| Exa Adapter bridge | 已实现 |
| Golden fixtures (离线可重现) | 已实现 (7/12 场景) |
| 原始 Skill 未修改 | 已保留 |

---

## 2026-07-14: IDEA Review 验证与 P0 修正

### 新增测试

新增 `backend/tests/idea/`，用于覆盖 IDEA 评审的真实业务边界，而不把此类测试混入通用单元测试：

1. 使用 `FakeSearchProvider` 的离线端到端链路：Idea 特征 → 搜索 → 去重 → 排序 → 全文抓取 → 证据 → 新颖性 → Quality Gate → SQLite State 持久化。
2. Workflow checkpoint：每个步骤只能使 `PatentCaseState.revision` 增加一次。
3. SearchProvider 失败语义：MCP bridge 不可用时必须返回 `failed`，不能以空结果伪装成功。
4. 旧 `/api/run` IDEA SSE 边界：在 mock Agent 下保留 `patent-IDEA-analyzer` 的流式输出与 session ID。

### 修正项

- 修正 `WorkflowOrchestrator` 与 `StateStore` 对同一 checkpoint 各自递增 revision，导致每步 revision 增加两次的问题；现在只由 StateStore 持久化时递增。
- OpenCode 1.17.18 未提供 `opencode mcp call` 子命令。桥接层现会将非零退出、超时、空输出明确转为异常，`ExaAdapter` 再返回结构化 `failed` 响应，避免误报成功。

### 验证结果与边界

- `backend/.venv/bin/python -m pytest backend/tests -q`：**111 passed**。
- 实际 `opencode mcp list` 发现当前 `https://mcp.exa.ai/mcp` 连接失败（SSE error），因此真实 Exa 搜索/抓取不在本次通过范围内。
- P0 是可测试的基础设施；现有 `/api/run` 仍直接启动原始 Skill，尚未接入 Case API、Workflow Orchestrator 和新 Provider。该接入属于设计文档的 P1-04，不能宣称已经完成新架构的端到端替换。
