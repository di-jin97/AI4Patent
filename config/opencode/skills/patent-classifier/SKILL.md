---
name: patent-classifier
description: >
  Classify patents against a hierarchical technical tag taxonomy. Trigger on:
  "专利分类", "技术标签", "patent tagging", "patent taxonomy mapping",
  "tag these patents", "classify these patents", or any request to map
  patents to a structured technology classification. User supplies a patent
  list (with or without metadata) and a tag hierarchy; skill fills missing
  data, classifies each patent, and outputs a structured Excel report.
---

# Patent Classifier

将一批专利按层级技术标签体系进行分类标引，输出结构化 Excel 报告。

---

## Core Principles

| # | Principle | Detail |
|---|-----------|--------|
| 1 | **Match the innovation core, not the application scenario** | A storage control algorithm for AI goes under 硬件/工程, not AI存储 |
| 2 | **Prefer the deepest level** | Assign to L2 when possible; fall back to L1 only when L2 is ambiguous |
| 3 | **When cross-domain, pick the innovation center of gravity** | Mention secondary domains in the reason, but classify by the primary innovation |
| 4 | **High-confidence only with clear data** | "高" requires clear abstract + unique tag match; "低" requires explicit flagging |
| 5 | **Family consistency is mandatory** | Same family → same classification; flag and reconcile any divergence |
| 6 | **Only search what's missing** | Skip retrieval if title + any technical description field already exists |

---

## Workflow

```
Phase A — Prepare
  Step 0  前置检查 — 解析输入、检测已有数据和分类
  Step 1  确认标签体系
Phase B — Enrich
  Step 2  专利信息采集（仅对缺失数据的专利）
Phase C — Classify
  Step 2.5 同族聚类推断（可选优化，≥10件自动开启）
  Step 3  逐件分类标引
Phase D — Verify & Output
  Step 4  质量自检
  Step 5  输出 Excel + 摘要
```

---

## Phase A: Prepare

### Step 0: 前置检查

#### 0.1 输入解析

两个必需输入：**专利清单** 和 **标签体系**。

扫描专利清单的列名，识别已有字段：

| 标准字段 | 常见列名变体 |
|---------|-------------|
| 专利号 | 专利号, Patent No., 公开号, patent_number |
| 标题 | 标题, Title, 发明名称 |
| 摘要 | 摘要, Abstract |
| 权利要求 | 权利要求, Claims, Claim1 |
| 技术方案 | 技术方案, Technical Solution, 技术手段 |
| 技术问题 | 技术问题, Technical Problem |
| 技术功效 | 技术功效, Technical Effect |
| 申请人 | 申请人, Assignee, Applicant |

如专利清单或标签体系缺失，询问用户。

#### 0.2 已有元数据检测

判断哪些专利需要从外部检索信息：

- **数据充分**（免检索）：已有标题 + 任一技术描述字段（摘要 / 权利要求 / 技术方案 / 技术问题 / 技术功效）
- **数据部分缺失**：有标题但无技术描述字段 → 补充检索
- **仅有专利号** → 完整检索

Also scan for an existing classification column (e.g. "一级分类", "分类"). If present, flag it for user confirmation — do not blindly overwrite.

#### 0.3 工具可用性检查

执行检索前确认 `exa_web_search_exa` / `exa_web_fetch_exa` 可用。若不可用，在报告开头明确告知用户，仅基于已有数据完成分类。

---

### Step 1: 确认标签体系

确认用户使用的标签体系版本和层级。

#### Default Taxonomy (Storage Technology Domain, 2-level)

This is the **built-in default** for the storage domain. If the user provides their own taxonomy (any domain), use theirs instead.

| 一级分类 (L1) | 二级分类 (L2 — representative technical directions) |
|--------------|---------------------------------------------------|
| 存储介质 | NAND/NOR Flash, SSD, HDD, SCM, 相变存储, 磁阻存储 |
| 硬件/工程 | 主控芯片, 通道架构, 热设计, 接口电路 |
| 协议层 | NVMe, SCSI, SATA, NVMe-oF, Fibre Channel, iSCSI |
| 数据效率 | 压缩, 重删, 分层存储, 缓存, 预取 |
| 数据保护 | RAID, EC纠删码, 快照, 备份, 加密, 安全删除 |
| AI存储 | 训练数据加速, 向量数据库, AI推理存储优化 |
| 存储平台与服务 | 分布式存储, 对象存储, 文件系统, 存储虚拟化 |
| 其他 | 存储管理软件, QoS, 监控告警；以及不属于上述类别的（如光存储, DNA存储, 存算一体等前沿方向） |

> **Override rule:** If the user supplies any other taxonomy (e.g. semiconductor, automotive, medical devices), discard the default and use the user's taxonomy. Always confirm with the user before proceeding.

---

## Phase B: Enrich

### Step 2: 专利信息采集

仅对 Step 0.3 标记为"需检索"的专利执行。

**检索策略：**
1. 优先直接构造 Google Patents URL 抓取：`https://patents.google.com/patent/{专利号}/en`
2. 失败则用 `exa_web_search_exa` 搜索：`patents.google.com patent {专利号}`
3. 从结果页提取：标题、摘要、申请人

每件专利最多搜索 3 次，搜索不到的标记"待确认"。

---

## Phase C: Classify

### Step 2.5: 同族聚类推断（可选优化）

若专利数量 ≥ 10 件，扫描全部专利元数据，识别同族关系：

**同族判定规则：**
- 相同申请人 + 相同优先权日/申请日 + 近似标题 → 同族
- 不同国家的同标题专利（如 US...B2 和 CN...A）→ 同族对应

**推断策略：**
- 族内已有 1 件数据充分 → 分类结果推断给同族其他成员，置信度标记"中"，理由标注"基于同族推断"
- 族内全部缺失 → 仅对 1 件"种子"专利检索，其余推断

---

### Step 3: 逐件分类标引

#### 3.1 自顶向下匹配

**分类依据优先级（从高到低）：**
1. **权利要求 / 技术方案 / 技术手段** — 最能体现核心技术特征
2. **技术问题 + 技术功效** — 辅助确认创新方向
3. **摘要** — 概述性技术描述
4. **标题** — 技术领域定位参考

具体步骤：
1. 按优先级阅读可用字段，识别核心技术创新点
2. 匹配一级分类（哪个大类），再匹配二级分类（哪个技术方向）
3. 选定最佳标签路径，撰写 1-3 句分类理由

#### 3.2 置信度评估

| 置信度 | 条件 |
|--------|------|
| 高 | 摘要清晰，标签唯一匹配 |
| 中 | 摘要模糊或跨两个领域但主次可判 |
| 低 | 摘要缺失或由同族推断 |

#### 3.3 边界 Case 消歧示例（存储领域）

以下示例帮助处理存储专利常见的分类边界场景：

**Case 1: SSD 垃圾回收 vs 文件系统 TRIM**
- 摘要："一种SSD控制器中的垃圾回收调度方法，根据写入放大率动态选择回收候选块..."
- 分类：**硬件/工程 -> 主控芯片**（创新是控制器内部GC算法，属固件/FTL层）
- 如果摘要说"一种文件系统层基于TRIM命令的空间回收策略" → **数据效率 -> 分层存储/缓存**（或**协议层**，看TRIM是否涉及协议扩展）

**Case 2: 存储加密 vs 数据保护**
- 摘要："一种基于硬件AES引擎的固态盘实时加密电路，加解密吞吐达6GB/s..."
- 分类：**硬件/工程 -> 接口电路**（创新是硬件加解密加速电路）
- 如果摘要说"一种密钥管理与分发的存储加密框架，支持多租户密钥隔离" → **数据保护 -> 加密**（创新是密钥管理方案本身）

**Case 3: NVMe-oF 存储网络 vs RDMA 传输**
- 摘要："一种NVMe-oF目标端命令调度优化方法，减少队列深度波动带来的时延抖动..."
- 分类：**协议层 -> NVMe-oF**（创新是NVMe-oF协议的传输优化）
- 如果摘要说"一种RDMA网络中的拥塞控制算法，降低长距离传输的丢包率" → **其他**（更偏向通用网络协议，非存储专属）

**Case 4: 向量数据库 — AI存储 vs 存储平台**
- 摘要："一种基于HNSW图的近似最近邻搜索索引结构，支持SSD持久化存储..."
- 分类：**AI存储 -> 向量数据库**（创新核心是向量索引+存储的结合）
- 如果摘要说"一种分布式向量数据库的集群扩缩容和负载均衡方法" → **存储平台与服务 -> 分布式存储**（创新是系统架构层）

**Case 5: Cache 分层 vs 冷热数据迁移**
- 摘要："一种基于IO频次统计的SSD-HDD冷热数据分层放置方法，热数据驻留SSD、冷数据下沉HDD..."
- 分类：**数据效率 -> 分层存储**（创新核心是冷热判定的数据放置策略）
- 如果摘要说"一种分布式混合存储系统中的缓存一致性协议" → **存储平台与服务 -> 分布式存储**（创新在分布式一致性，不在冷热判定本身）

**Case 6: 纠删码 vs 分布式存储架构**
- 摘要："一种适用于NVMe SSD阵列的RS纠删码并行编码硬件加速器，减少编码延迟..."
- 分类：**硬件/工程 -> 主控芯片**（或**数据保护 -> EC纠删码**，看创新重点在硬件加速电路还是EC算法本身）
- 如果摘要说"一种跨地域分布式存储系统中的纠删码条带布局优化" → **存储平台与服务 -> 分布式存储**（创新在系统级条带策略）

**Case 7: ZNS SSD 分区存储 — 存储介质 vs 协议层**
- 摘要："一种ZNS SSD的主动数据迁移策略，在分区内重排有效数据减少写放大..."
- 分类：**存储介质 -> SSD**（创新是ZNS特性下的FTL/数据放置策略）
- 如果摘要说"一种ZNS协议扩展，新增分区重置优先级字段" → **协议层 -> NVMe**（创新在协议扩展本身）

---

## Phase D: Verify & Output

### Step 4: 质量自检

Run all checks below. For each check that fails, log a warning and note it in the report summary.

#### Check 4.1 — Distribution sanity
- **Balance**: No single L1 tag should exceed 50% of total patents unless the scope genuinely warrants it. If >50%, flag for review.
- **Depth**: If ≥30% of patents only have an L1 tag (no L2), warn: "二级分类不足，建议细化."
- **Empty tags**: Any L1 tag with 0 patents is acceptable (not all categories need coverage).

#### Check 4.2 — Confidence distribution
- **Low-confidence ratio**: If low-confidence patents >20% of total, warn: "低置信度占{X}%，建议复核缺失数据的专利."
- **High-confidence floor**: If high-confidence patents <30%, warn: "高置信度偏低，数据质量可能不足."
- **Correlation**: If all low-confidence patents share the same missing field pattern (e.g. all lack abstracts), surface a root-cause note.

#### Check 4.3 — Family consistency
- **Same family, same tag**: Scan all identified families. Any divergence → list specific patent pairs and re-classify.
- **Cross-family drift**: If two very similar patents from different assignees fall into different L1 tags, verify the distinction is intentional.

#### Check 4.4 — IPC/CPC cross-validation
- If CPC/IPC data is available (from Google Patents or user data), check for major contradictions:
  - `G11C` → should map to 存储介质 or 硬件/工程
  - `G06F3/06` → typically 协议层 or 存储控制
  - `H04L29/08` → distributed storage related
  - Major mismatch (e.g. `A61K` pharmaceutical CPC but classified as 存储介质) → flag for review.
- If no CPC data is available, skip this check silently.

#### Check 4.5 — Edge-case audit
- Re-scan any patent whose abstract contains ambiguous boundary keywords: "cache", "encrypt", "RAID", "NVMe", "GC", "FTL", "ZNS", "vector", "RDMA".
- Verify each against the boundary case rules in Step 3.3.
- If any audit finds a mismatch, correct it and note the correction in the report.

#### Check 4.6 — Reason quality
- Ensure every patent has a non-empty "理由" column (1-3 sentences).
- Reject boilerplate like "根据摘要分类" — the reason must reference a specific technical feature from the patent.

---

### Step 5: 输出

#### 5.1 Excel

| 列名 | 说明 |
|------|------|
| 序号 | 编号 |
| 专利号 | 专利号 |
| 标题 | 标题 |
| 申请人 | 申请人 |
| 一级分类 | 最佳匹配的一级类别 |
| 二级分类 | 最佳匹配的二级类别 |
| 置信度 | 高/中/低 |
| 理由 | 分类依据（1-3句） |
| 分类来源 | 自动分类 / 用户已有 / 同族推断 |

格式：表头蓝色背景 #4472C4，正文 Arial 10pt，自动换行，全单元格细边框。低置信度行浅黄色高亮。

#### 5.2 摘要

```
━━━ 专利分类报告 ━━━
标签体系: {来源}
专利总数: {N}

分类分布:
  存储介质:       {N} 件
  硬件/工程:      {N} 件
  协议层:         {N} 件
  ...

质量概览:
  高置信度: {X} 件
  中置信度: {Y} 件 ← 建议抽检
  低置信度: {Z} 件 ← 建议复核

质量检查结果:
  [✓] 分布合理性
  [✓] 置信度分布
  [✓] 同族一致性
  [✓] IPC/CPC 交叉验证
  [✓] 边界Case审计
  [✓] 理由质量
  警告: {如果有任何检查失败, 列出警告项}
```