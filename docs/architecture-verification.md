# Architecture Verification Report

| 项 | 内容 |
|---|---|
| 版本 | 0.1.0 |
| 日期 | 2026-07-13 |
| 状态 | P0-01 completed |
| 依赖 | 无 |

## 1. 环境确认

| 项目 | 值 | 状态 |
|---|---|---|
| Python | 3.12.3 | confirmed |
| Pydantic | 2.13.4 | confirmed |
| FastAPI | 0.139.0 | confirmed |
| OpenCode CLI | 1.17.18 | confirmed |
| OpenCode provider | DeepSeek v4-pro | confirmed |
| Exa MCP | remote (`https://mcp.exa.ai/mcp`), enabled | confirmed |
| OS | Linux | confirmed |
| pip deps | fastapi, uvicorn, httpx, python-multipart | confirmed |

## 2. 仓库结构事实

| 区域 | 路径 | 说明 |
|---|---|---|
| Backend | `backend/main.py` (258 lines) | FastAPI app, 配置/文件/运行 API |
| Client | `backend/opencode_client.py` (166 lines) | 子进程调用 opencode run, SSE 流解析 |
| Frontend | `frontend/index.html` (364 lines) | 单页 SPA, 5 tab, SSE streaming |
| Config | `config/opencode/opencode.json` | model=deepseek/deepseek-v4-pro, mcp.exa |
| Skill | `config/opencode/skills/patent-IDEA-analyzer/SKILL.md` (1104 lines) | 原始业务规则 |
| Tests | **无** | 项目中不存在任何测试文件 |
| `backend/patent_analysis/` | **不存在** | 设计文档建议的新目录 |

## 3. 已证实项

1. **FastAPI 可以新增路由**: `backend/main.py` 使用标准 FastAPI 模式，可直接添加新的 router 或 endpoint。
2. **OpenCode 可作为子进程调用**: `opencode_client.py` 证明可通过 `opencode run --format json` 启动 agent 会话并解析 JSON 事件流。
3. **Exa MCP 可通过 Agent 调用**: 配置文件和 AGENTS.md 证明 Agent 会话中可使用 `exa_web_search_exa` 和 `exa_web_fetch_exa` 工具。
4. **Pydantic 2.x 可用**: 可直接使用 Pydantic BaseModel 定义数据模型和 JSON Schema。

## 4. 未证实项（待核实）

1. **Python 端能否直接调用 Exa MCP**: 当前只能通过 OpenCode Agent 会话间接调用 Exa 工具。无直接 MCP client SDK。需要实现 **constrained agent bridge**（设计文档 Section 7.4）。
2. **OpenCode 是否提供可由 Python 调用的 MCP tool API**: 未找到相关文档或 API。

## 5. 关键决策

| 决策 | 结论 | 依据 |
|---|---|---|
| State storage | SQLite (同机) | Python 内置，无需新服务 |
| Schema | Pydantic v2 + JSON Schema export | 已在依赖中 |
| Search bridge | 先实现 ExaAdapter bridge (通过 Agent 会话调用 Exa 工具) | 直接 MCP SDK 不可用 |
| Tests | pytest + fixtures | 按设计文档 P0-02 创建 Golden fixtures |
| 向后兼容 | 不修改 `/api/run` logic，新增并行路由 | feature flag 回滚 |

## 6. MCP / Exa 调用面分析

当前 Exa 在两个层面被使用:
1. **OpenCode Agent 运行时**: 通过 `mcp.exa` 的 remote MCP 配置，Agent 可直接调用 `exa_web_search_exa` / `exa_web_fetch_exa`
2. **Python 后端**: 无直接调用路径

**Bridge 方案**: Python 端构造结构化的 `SearchRequest`，启动一个 mini OpenCode session（专用检索 Skill），该 session 仅负责执行 Exa 工具调用并返回经过 Schema 校验的 `SearchResponse` JSON。

## 7. 环境变量整理

| 变量 | 当前用途 | 建议新增 |
|---|---|---|
| `XDG_CONFIG_HOME` | opencode_client 设置 = `config/` | — |
| `XDG_DATA_HOME` | opencode_client 设置 = `data/` | — |
| `OPENCODE_EXE` | 指定 opencode 二进制路径 | — |
| — | — | `AI4P_CASE_DB_PATH` |
| — | — | `AI4P_CASE_ROOT` |
| — | — | `AI4P_SEARCH_PROVIDER` |
| — | — | `AI4P_EXA_TIMEOUT_SECONDS` |
