---
name: patent-search-planner
description: Plan independent patent searches from normalized technical features.
---

# 检索规划

输入为特征和检索词 JSON。输出 `queries` JSON，每项有 `query_text`、`phase`（A-D）和 `intent`；至少规划核心组合与关键特征两批检索。不得声称已经检索或输出文献结论。

这是纯规划节点：不得调用任何工具、不得读取或写入文件、不得执行实际检索。只在最终文本响应中输出一个合法 JSON 对象，禁止 Markdown、解释文字或文件路径。对象格式为：`{"queries":[{"query_text":"...","phase":"A","intent":"..."}],"strategy":"..."}`。
