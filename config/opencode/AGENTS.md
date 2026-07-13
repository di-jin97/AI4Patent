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

**统一使用 EXA MCP 工具进行搜索和网页抓取**，禁止使用 `webfetch`、`web_fetch`、`web_search` 等内置工具（本地网络无法访问 Google 等海外站点，只有 EXA 走海外代理能成功）。

### 工具1：exa_web_search_exa（关键词搜索）

用途：按关键词搜索网页，返回标题、URL、摘要片段。适合找相关专利、论文、产品文档。

```
exa_web_search_exa(query="SSD write compression NAND flash patent", numResults=20)
```

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `query` | 搜索关键词，用英文搜索海外内容，用中文搜索国内内容 | -- |
| `numResults` | 返回结果数量 | 10-20（精确检索用 20） |

### 工具2：exa_web_fetch_exa（抓取指定网页全文）

用途：给定一个 URL，返回该页面的完整文本内容。适合抓取专利全文、论文详情页、产品白皮书。

```
exa_web_fetch_exa(urls=["https://patents.google.com/patent/CN102063547B/en"])
```

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `urls` | 要抓取的 URL 数组（可传多个） | 单次 1-3 个 |
| `maxCharacters` | 返回内容最大字符数 | 专利全文用 100000（默认 50000 可能截断 claims） |

### 专利号 -> URL 拼接规则

给定专利号，构造 Google Patents URL 直接抓取全文：

| 专利号格式 | 拼接 URL | 示例 |
|-----------|---------|------|
| CN + 数字 + A/B | `https://patents.google.com/patent/{专利号}/en` | CN102063547B -> `https://patents.google.com/patent/CN102063547B/en` |
| US + 数字 + B1/B2 | 同上 | US10964349B2 -> `https://patents.google.com/patent/US10964349B2/en` |
| EP + 数字 + A1/B1 | 同上 | EP1234567A1 -> `https://patents.google.com/patent/EP1234567A1/en` |
| WO + 数字 + A1 | 同上 | WO2020123456A1 -> `https://patents.google.com/patent/WO2020123456A1/en` |

**通用规则**：任何专利号直接拼 `https://patents.google.com/patent/{专利号}/en`，用 `exa_web_fetch_exa` 抓取。

### 常见搜索场景

| 场景 | 工具 | 示例 |
|------|------|------|
| 获取专利全文 | `exa_web_fetch_exa` | `exa_web_fetch_exa(urls=["https://patents.google.com/patent/CN102063547B/en"], maxCharacters=100000)` |
| 搜索相关专利 | `exa_web_search_exa` | `exa_web_search_exa(query="SSD write compression patent", numResults=20)` |
| 搜索学术论文 | `exa_web_search_exa` | `exa_web_search_exa(query="NAND flash write amplification reduction paper", numResults=10)` |
| 搜索友商产品文档 | `exa_web_search_exa` | `exa_web_search_exa(query="Samsung SSD TurboWrite technology whitepaper", numResults=10)` |
| 抓取友商产品页面 | `exa_web_fetch_exa` | `exa_web_fetch_exa(urls=["https://www.samsung.com/semiconductor/ssd/"])` |

### 注意事项

1. **EXA 走海外服务器代理**，不受本地网络限制，能访问 Google Patents 等被墙站点
2. **专利全文较长**，默认 `maxCharacters=50000` 可能截断 claims 部分，建议设为 `100000`
3. **搜索用英文**：海外专利和论文用英文关键词搜索效果更好；中文专利可用中文搜索
4. **不要用内置 `webfetch`**：它走本地网络，Google 等海外站点会超时
5. 有把握的事实直接回答，不确定时再用 EXA 搜索验证
