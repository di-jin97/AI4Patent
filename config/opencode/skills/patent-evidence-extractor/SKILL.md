---
name: patent-evidence-extractor
description: Classify source-grounded passages against supplied feature IDs.
---

# 证据映射

只处理 INPUT 里给出的段落，输出 JSON `matches`。每个 match 必须包含 `feature_id`、`locator`、`quoted_text`；quoted_text 必须逐字出现在输入段落中。证据不足时输出空数组，绝不补造。
