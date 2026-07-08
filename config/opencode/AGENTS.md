# Global OpenCode Rules

## Windows PowerShell Encoding Fix

On Windows with Chinese/Japanese/Korean locale, the console encoding defaults to GB2312/GBK (CodePage 936).
When running PowerShell commands through the bash tool, **always prepend** the UTF-8 encoding command:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
```

For example, instead of running:
```
Get-ChildItem -File
```

Run:
```
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); Get-ChildItem -File
```

This ensures Chinese characters display correctly in command output.

### Python Encoding Fix

Although `PYTHONIOENCODING=utf-8` is set as a system environment variable, the bash tool's pwsh subprocess may not always inherit it.
When running Python commands, **also prepend** the UTF-8 encoding fix:

```powershell
$env:PYTHONIOENCODING='utf-8'; python your_script.py
```

For example:
```
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); $env:PYTHONIOENCODING='utf-8'; python -c "print('中文测试 ✅')"
```

**CRITICAL**: NEVER use inline `python -c "..."` when the Python code contains Chinese characters. 
PowerShell will fail to parse Chinese characters in `-c` strings even with encoding fixes.
Instead, **always write Python code to a `.py` file first** (use temp dir `C:\Users\j00815423\AppData\Local\Temp\opencode\`), then execute the file:

```powershell
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); $env:PYTHONIOENCODING='utf-8'; python script.py
```

### Node.js
Node.js already handles UTF-8 correctly on this system - no fix needed.

## Search Rule

Use whichever search/fetch tool fits the task best — `exa_web_search_exa`, `exa_web_fetch_exa`, `webfetch`, or reading local files. Not constrained to Exa.

- Answer directly from existing knowledge for facts you are confident about — don't search unnecessarily.
- Only verify externally when uncertain about specifics (version numbers, file names, issue IDs, newly changed facts).
- Exa MCP is still configured in `opencode.json` as a remote server (`https://mcp.exa.ai/mcp`) and remains a good option for web search/fetch.

Do NOT scrape search engine result pages with `webfetch` (useless output).

## Self-Improvement

Learnings are stored in `~/.config/opencode/.learnings/`. Review before major tasks.
Initialize: `mkdir -p ~/.config/opencode/.learnings/`

## Patent Analysis Best Practices

When using the `storage-patent-deepdive` skill:
1. **分类粒度**: 6-8个分类，每件专利标主/次标签+置信度
2. **要件分解**: 全部专利输出到Excel+Claim 1按分句拆成独立技术特征(F1/F2/F3)
3. **技术路线对比**: 归纳各家"方案特征签名"（如"几何精度驱动型"），而不仅是列表格
4. **申请人画像**: 每家>3个具体特征，每个关联到专利号
5. **技术趋势**: 用直白三段式（最新技术→新旧差异→业界方向），不用"拐点/收敛/分化"等抽象框架
6. **重点专利数量**: 前30%（至少5件），不是固定5-8件