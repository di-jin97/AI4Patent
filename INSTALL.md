# AI4P 专利 AI Agent 平台 — 安装与使用教程

## 一、别人电脑需要装什么？（依赖说明）

| 依赖 | 要不要装 | 说明 |
|------|---------|------|
| **Python 3.10+** | ✅ 必装 | FastAPI 后端跑在 Python 上。去 python.org 下载安装，勾选 "Add to PATH" |
| **opencode** | ❌ 不用装 | 软件已自带 `bin/opencode/opencode.exe`（独立二进制） |
| **Node.js** | ❌ 不用装 | opencode 是 Bun 编译的独立 exe，不依赖 Node |
| **LLM API Key** | ✅ 必配 | 火山方舟/智谱/OpenAI 等，用来调用大模型 |

**结论：别人只需装 Python + 配 API Key，不用装 opencode/Node。**

---

## 二、安装步骤（给别人电脑）

### 第 1 步：解压
把 `AI4P` 整个文件夹拷到对方电脑任意位置（如 `D:\AI4P` 或 `C:\AI4P`），解压。

### 第 2 步：装 Python（如果没有）
- 去 https://python.org 下载 Python 3.10+
- 安装时**勾选 "Add Python to PATH"**
- 验证：打开 PowerShell 输入 `python --version`，显示版本号即可

### 第 3 步：配 API Key
编辑 `data/opencode/auth.json`，填入你的大模型 API Key：
```json
{
  "agent-plan": { "apiKey": "你的火山方舟key" },
  "zai": { "apiKey": "你的智谱key" }
}
```
（如果用别的 provider，同步改 `config/opencode/opencode.json` 里的 model 和 provider 配置）

### 第 4 步：启动
双击 `start.ps1`（或在 PowerShell 里运行 `.\start.ps1`）。
- 首次启动会自动创建虚拟环境 + 装依赖（约 1 分钟）
- 装完自动启动服务 + 打开浏览器
- 看到浏览器打开 `http://localhost:8001` 即成功

### 第 5 步：使用
- 左侧选功能模块（IDEA评审/业界专利分析/技术路线/创新性检索/PCT评审/侵权挖掘）
- 输入框写内容（或右侧上传文件勾选喂给模型）
- 点「执行 ▶」等结果（1-3 分钟）
- 结果出来后可「追问」（同一 session 继续对话）
- 模型生成的文件在右侧「模型生成文件」区下载

### 停止
任务管理器结束 `python.exe` 进程，或 PowerShell 运行：
```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## 三、打包方法（你把软件给别人）

### 打包前清理
在 D:\AI4P 目录下，删除以下测试残留：
```
backend\.venv\          （虚拟环境，别人重装）
backend\test_*.py       （测试脚本）
backend\chk*.py
backend\diag*.py
backend\ftest*.py
backend\idtest*.py
backend\kvtest*.py
backend\kvnew.py
backend\longtest.py
backend\probe_sse.py
backend\realtest.py
backend\verify.py
backend\vnew.py
backend\vsimple*.py
backend\mkdoc.py
backend\check.js
backend\test_body.json
backend\test422.py
backend\api*.log
backend\api*.err
isolated\               （测试目录）
.pytest_cache\
logs\*.log              （日志）
workspace\test.docx     （测试文件）
workspace\report.docx
workspace\gen_report.js
data\opencode\opencode.db*  （session 数据库）
```

### 打包
把清理后的 `AI4P` 文件夹压缩成 zip：
```powershell
Compress-Archive -Path "D:\AI4P" -DestinationPath "D:\AI4P-package.zip"
```

### 别人拿到 zip 后
解压 → 装 Python → 配 Key → 运行 start.ps1 → 用。

---

## 四、目录结构说明

```
AI4P/
├── start.ps1                    ← 启动脚本（给别人用，双击运行）
├── dev.ps1                      ← 开发启动脚本（前台显示日志，自己调试用）
├── INSTALL.md                   ← 本教程
├── bin/opencode/opencode.exe    ← opencode 引擎（自带，不用装）
├── config/opencode/             ← opencode 配置（自包含）
│   ├── opencode.json            ← 模型配置（glm-5.2, output 16384）
│   ├── AGENTS.md                ← 规则
│   └── skills/                  ← 47 个 skill（含 6 个专利模块对应 skill）
├── data/opencode/               ← opencode 数据
│   └── auth.json                ← API Key（别人填自己的）
├── backend/                     ← FastAPI 后端
│   ├── main.py                  ← 主程序
│   ├── opencode_client.py       ← opencode run 封装
│   └── requirements.txt         ← Python 依赖
├── frontend/index.html          ← 前端工作台
├── workspace/                   ← 文件工作区
│   └── uploads/                 ← 用户上传的文件
└── logs/                        ← 运行日志
```

---

## 五、常见问题

**Q: 启动报 "python 不是内部命令"**
A: Python 没装或没加 PATH。重装 Python 勾选 "Add to PATH"。

**Q: 点执行后没反应 / 422 错误**
A: 确认 auth.json 的 API Key 填对了，opencode.json 的 model 配置正确。

**Q: 结果被截断（报告不完整）**
A: opencode.json 里 glm-5.2 的 `limit.output` 已调到 16384。如还不够，可再调大。

**Q: 想换模型**
A: 改 `config/opencode/opencode.json` 的 `model` 字段 + auth.json 配对应 provider key。

**Q: 端口 8001 被占用**
A: 停掉占用进程，或改 start.ps1 / dev.ps1 里的端口号。
