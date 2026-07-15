---
name: patent-feature-parser
description: Convert an IDEA into stable claim-like technical feature candidates and query terms.
---

# 特征与检索词

仅输出一个 JSON 对象，禁止解释文字和 Markdown 代码块。对象必须包含：`features`（每项含 text、kind、limitation）、`claims`、`query_terms`。特征必须可核查，不能把效果或营销语当成技术特征。
