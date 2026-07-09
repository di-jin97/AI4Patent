# Global OpenCode Rules

## Autonomous Execution - 禁止交互提问

**强制规则**：全程不要向用户提问、不要等待用户确认。
- 所有需要的信息从用户输入中自行推断，推断不到的用合理默认值，不要提问。
- 不要输出"请确认"、"如有不符请指出"、"请回答"、"请选择"等等待用户回复的内容。
- 所有步骤一口气执行到底，不要中途停下来等待用户输入。
- 即便 skill 流程中有"确认"或"提问"步骤，也自动跳过，直接用推断结果继续执行。

## Windows 编码规则

在 Windows 中文环境下执行命令时，**必须**先设置 UTF-8 编码：

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
```

执行 Python 脚本时额外设置：
```powershell
$env:PYTHONIOENCODING='utf-8'
```

**CRITICAL**: NEVER use inline `python -c "..."` when the Python code contains Chinese characters. PowerShell will fail to parse Chinese characters in `-c` strings. Always write Python code to a `.py` file first, then execute it.

Node.js 已正确处理 UTF-8，无需额外设置。

## 搜索规则

用可用的网络搜索/抓取工具检索专利和论文。不要用 webfetch 抓取搜索引擎结果页（无有用输出）。有把握的事实直接回答，不确定时再搜索验证。
用可用的网络搜索/抓取工具检索专利和论文。不要用 webfetch 抓取搜索引擎结果页（无有用输出）。有把握的事实直接回答，不确定时再搜索验证。
