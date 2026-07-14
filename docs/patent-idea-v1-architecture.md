# Patent IDEA Review 1.0 架构拆分与实施契约

## 1. 组件边界

```text
FastAPI / UI
  └─ CaseApplicationService
       ├─ WorkflowOrchestrator             状态、预算、恢复、步骤编排
       ├─ SkillRunner                      受约束调用渐进式 OpenCode Skill
       ├─ PatentDataProvider               专利事实读取接口
       │   ├─ GooglePatentsProvider        页面检索/抓取适配器
       │   └─ BigQueryPatentProvider       可选批量发现适配器
       ├─ Domain services                  日期、去重、证据、新颖性、创造性、质量门
       ├─ ArtifactRepository               原文 blob、索引、报告
       └─ Renderers                        Chat/MD/JSON/DOCX/XLSX
```

依赖方向只能从上到下：Skill、workflow 和 evaluator 不能直接请求 Google；它们只能调用 Provider 契约。Provider 不能导入领域结论模型。

## 2. 核心契约

### 2.1 `PatentDataProvider`

```python
class PatentDataProvider(Protocol):
    async def search(self, request: PatentSearchRequest) -> PatentSearchResponse: ...
    async def get_biblio(self, request: BiblioRequest) -> BiblioResponse: ...
    async def get_sections(self, request: SectionRequest) -> SectionResponse: ...
    async def find_passages(self, request: PassageSearchRequest) -> PassageSearchResponse: ...
    async def get_relations(self, request: RelationsRequest) -> RelationsResponse: ...
```

所有 response 必含 `request_id`、`status`、`source`、`retrieved_at`、`source_url`、`raw_artifact_id` 或 `content_hash`。`failed`/`partial` 是合法状态，不能伪装为空成功。

### 2.2 `SkillRunner`

```python
class SkillRunner(Protocol):
    async def run_json(
        self, skill_name: str, input_model: BaseModel, output_type: type[T],
        *, state_revision: int, artifact_refs: list[str]
    ) -> T: ...
```

实现将调用 OpenCode，但调用提示只包含 Skill 名、JSON Schema、当前 State 切片和受限 artifact 片段；输出必须为 JSON，解析/Schema 失败只允许一次修复调用，随后进入可恢复失败状态。

### 2.3 ToolCall 服务内部层

```text
tool contract → provider facade → rate limiter/cache → source transport
                                      ↓
                            parser → artifact repository
```

HTML parser 只把页面变成原始、可定位事实；文本切块、特征检索和引用定位要可重放。可选的 OpenCode ToolCall/MCP façade 只包装 Provider，不复制业务规则。

## 3. 目标 workflow

| Step | 输入 | 主责任方 | 输出 |
| --- | --- | --- | --- |
| intake | Idea/模式 | `patent-idea-intake` | 审查范围、日期、法域 |
| features | intake | `patent-feature-parser` | FeatureSet、claim draft、词库 |
| plan | features/预算 | `patent-search-planner` | A–D QueryPlan |
| search | QueryPlan | Provider + normalizer/ranker | documents/search runs |
| fulltext | ranked docs | Provider | sections/raw artifacts |
| evidence | features + sections | `patent-evidence-extractor` | EvidenceItem 候选 → validator |
| novelty | evidence | deterministic novelty engine | 覆盖矩阵/结论 |
| inventive | novelty + evidence | inventive Skill + validator | D1/D2 routes |
| commercial | state | commercial Skill | value result |
| quality | frozen state | deterministic quality gate | passed/warnings/errors |
| report | quality-passed state | renderer Skill/template | artifacts |

## 4. 渐进式 Skill 目录

```text
config/opencode/skills/
  patent-idea-entry/
  patent-idea-intake/
  patent-feature-parser/
  patent-search-planner/
  patent-evidence-extractor/
  patent-inventiveness/
  patent-commercial-value/
  patent-examiner-opinion/
  patent-report-renderer/
```

每个目录只有短入口和特定 reference；不得复制旧 Skill 的全部 1,100 行。旧 Skill 在迁移期间是规则来源和回归基线。

## 5. 实施顺序

1. 建立 ToolCall contracts、Google Provider、fixture parser、缓存与限流。
2. 建立 SkillRunner 与 intake/feature/search planner 子 Skill，替换当前基线特征和单查询。
3. 接入全文、段落定位、证据 Skill、新颖性真实结论。
4. 接入 D1/D2 创造性、价值、模拟审查意见和完整 renderer。
5. 使用 Legacy 对照测试和双跑报告，达到 PRD 门槛后切换默认。
