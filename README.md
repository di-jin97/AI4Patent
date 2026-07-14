# AI4Patent - 专利 AI Agent 工作台

基于 opencode 引擎的专利智能分析平台，集成 5 大专利分析模块，支持并行执行、文件上传下载、多轮追问。

IDEA 评审的目标架构见 [设计文档](docs/patent-innovation-analysis-agent-design.md)，原始完整 Skill 与当前结构化 1.0 的能力边界见 [版本对比](docs/idea-review-version-comparison.md)。

## 功能模块

| 模块 | Skill | 功能说明 |
|------|-------|---------|
| 💡 专利IDEA评审 | `patent-IDEA-analyzer` | 输入专利 Idea（文字描述/权利要求草稿/方案概述），执行多引擎全量检索，以专利审查员视角对新颖性和创造性进行系统评价，输出审查意见模拟报告 |
| 📊 业界专利分析 | `storage-patent-deepdive` | 输入一批存储领域专利，自动补全数据、分类标引、技术方案摘要、价值评分、Claim 1 要件分解、竞争格局分析、技术趋势研判 |
| 📋 PCT申请评审 | `patent-pct-review` | 输入 Excel 专利清单和 DOCX 申请文件，从创新性、可规避性、市场价值、落地产品、可取证性五个维度评分，排序后推荐进 PCT 的专利 |
| 💰 专利价值评估 | `patent-value-assessment` | 输入已授权专利，从权利要求稳定性、技术创新程度、业界侵权使用证据、技术时效性四个维度评估，输出价值等级（A/B/C/D）及维持/放弃建议 |
| ⚖️ 侵权挖掘 | `seek-cfp-patent` | 输入专利 Claim 1，拆分技术特征、搜索友商产品、逐特征加权比对，输出侵权分析报告 |

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.10+
- 网络访问（用于 EXA 搜索和模型 API）

### 安装

```powershell
git clone https://github.com/di-jin97/AI4Patent.git
cd AI4Patent
.\install.ps1
```

`install.ps1` 会自动完成：
1. 解压 opencode 引擎到 `bin/opencode/`
2. 创建 Python 虚拟环境并安装后端依赖
3. 创建 logs、data、workspace 等目录
4. 检查 API Key 配置状态

### 配置 API Key

安装完成后，启动服务并在界面中配置：

1. 运行 `.\start.ps1`（或 `.\dev.ps1`）
2. 浏览器打开 `http://localhost:8001`
3. 首次访问会弹出配置框，填入：
   - **Provider 名称**：`deepseek`
   - **Base URL**：`https://api.deepseek.com/v1`
   - **API Key**：你的 DeepSeek API Key
   - **模型名称**：`deepseek-v4-flash`
4. 点击保存即可使用

本仓库已预置 DeepSeek Flash 配置，默认模型为 `deepseek/deepseek-v4-flash`。DeepSeek 的 OpenAI 兼容 API 地址配置为 `https://api.deepseek.com/v1`，模型名为 `deepseek-v4-flash`。

### 启动

```powershell
# 方式一：后台启动（推荐）
.\start.ps1

# 方式二：前台启动（实时日志，开发调试用）
.\dev.ps1
```

启动后自动打开浏览器访问 `http://localhost:8001`。

### 停止

```powershell
.\stop.ps1
```

## 使用方法

### 基本流程

1. 选择上方功能模块按钮（如 💡 专利IDEA评审）
2. 在输入框中输入专利内容（专利号、技术方案描述、权利要求等）
3. 可选：上传相关文件（Excel 专利清单、DOCX 申请文件等），勾选后随请求发送给模型
4. 点击「执行」，等待 AI 分析完成（通常 1-5 分钟）
5. 结果在下方回答框中展示，支持 Markdown 格式
6. 可在追问框中继续提问，AI 会基于上下文回答

### 并行执行

5 个模块相互独立，支持并行运行：
- 在一个模块中提交任务后，可切换到其他模块继续提交
- 运行中的模块标签会显示橙色闪烁指示点
- 每个模块的输入、输出、追问状态独立保存，切换不丢失
- 每个模块可单独停止

### 文件管理

- 右侧文件管理区支持上传/下载/删除文件
- 上传文件后勾选，会随请求一起发送给模型
- 模型生成的文件也会显示在文件列表中

## 搜索能力

平台集成 EXA MCP 搜索引擎，支持：

- **专利全文获取**：通过专利号构造 Google Patents URL，使用 `exa_web_fetch_exa` 抓取完整专利文本（标题、摘要、权利要求、说明书）
- **关键词搜索**：使用 `exa_web_search_exa` 搜索相关专利、论文、产品文档、白皮书
- EXA 走海外服务器代理，不受本地网络限制，可访问 Google Patents 等海外站点

### 结构化 IDEA 评审 1.0

IDEA 页面默认走 `Case API → workflow → 渐进式 Skills → 自有 Google Patents ToolCall`。它会保存案件、SSE 进度、可恢复 checkpoint、全文定位证据、新颖性/创造性路线、商业预评估、模拟审查意见和八章报告。原 `patent-IDEA-analyzer` 保留为即时回滚入口。

Google Patents 的直接访问默认关闭，避免未经确认的自动化访问。确认访问政策、网络与速率限制后再显式启用：

```bash
export GOOGLE_PATENTS_DIRECT_ACCESS_ENABLED=true
```

若访问未启用或被 robots 拒绝，案件会以可解释错误结束，不会把空检索伪装成新颖性结论。需要立即回滚原 Skill 时设置：

```bash
export IDEA_STRUCTURED_BETA_ENABLED=false
```

### 搜索 MCP 与密钥维护

- **原 Skill 的 MCP 配置**：编辑 `config/opencode/opencode.json` 的 `mcp.exa`；可参考 `opencode.json.example`。
- **结构化 IDEA 的 Google 数据层**：`backend/patent_analysis/tools/google_patents.py` 暴露独立的检索、书目信息、章节和段落匹配 ToolCall；`backend/patent_analysis/adapters/google_patents.py` 仅做工作流兼容适配。
- **更换搜索服务**：实现 `backend/patent_analysis/tools/contracts.py` 的事实 ToolCall，再提供 `SearchProvider` 适配器并在 `backend/main.py` 注入；不要把服务差异写入工作流或 Skill。
- **模型密钥**：只保存在 `config/opencode/secrets/<provider>-api-key`。不要把密钥写入 JSON、日志或版本库，也不要在共享终端执行会打印已解析配置的调试命令。曾暴露或写入历史的密钥必须先在供应商后台轮换，历史清理应在密钥失效后再进行。

## 技术架构

```
AI4Patent/
├── backend/              # FastAPI 后端
│   ├── main.py           # API 路由（配置/文件/任务执行）
│   ├── opencode_client.py # opencode 引擎调用（支持并行任务）
│   └── requirements.txt   # Python 依赖
├── frontend/
│   └── index.html        # 单页前端（5模块并行 + 状态隔离）
├── bin/
│   ├── opencode/         # opencode 引擎（从 zip 解压）
│   └── opencode-windows-x64.zip
├── config/opencode/
   ├── opencode.json      # opencode 配置（模型 + EXA MCP）
   ├── AGENTS.md          # 全局规则（搜索指南、编码规则）
   └── skills/            # 5 个专利分析 Skill
       ├── patent-IDEA-analyzer/
       ├── storage-patent-deepdive/
       ├── patent-pct-review/
       ├── patent-value-assessment/
       └── seek-cfp-patent/
├── install.ps1           # 一键安装
├── start.ps1             # 后台启动
├── dev.ps1               # 前台启动（开发模式）
└── stop.ps1              # 停止服务
``+
### 技术栈

- **后端**：Python + FastAPI + Uvicorn
- **引擎**：opencode run（AI Agent 执行引擎）
- **前端**：原生 HTML/CSS/JS（单页应用）
- **搜索**：EXA MCP（海外代理搜索 + 网页抓取）
- **模型**：兼容 OpenAI API 格式的任意大模型（如 GLM-5.2）

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `install.ps1` | 一键安装：解压引擎、创建虚拟环境、安装依赖、创建目录 |
| `start.ps1` | 后台启动服务 + 自动开浏览器，关闭窗口后服务继续运行 |
| `dev.ps1` | 前台启动服务，终端实时显示日志，Ctrl+C 退出 |
| `stop.ps1` | 停止后台运行的服务 |

## License

MIT
