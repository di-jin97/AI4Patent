from pathlib import Path

import pytest

from backend.patent_analysis.domain.models import (
    CaseMeta, CaseRequest, CaseStatus, EvidenceItem, Feature,
    PatentCaseState, PriorArtDocument,
)
from backend.patent_analysis.services.novelty import evaluate_novelty
from backend.patent_analysis.steps import FeatureExtractionStep, SearchPlanningStep
from backend.patent_analysis.skills.runner import OpenCodeSkillRunner, RuleBasedSkillRunner, SkillRunner, _build_skill_prompt, _parse_json


@pytest.mark.asyncio
async def test_progressive_skills_have_independent_json_contracts():
    runner = RuleBasedSkillRunner()
    intake = await runner.run("patent-idea-intake", {"idea": "依据工作负载动态选择缓存层级"})
    features = await runner.run("patent-feature-parser", {"idea": "动态选择缓存层级；根据工作负载调整缓存"})
    plan = await runner.run("patent-search-planner", {"idea": "缓存", "query_terms": features["query_terms"]})
    assert intake["solution_summary"]
    assert len(features["features"]) == 2
    assert len(plan["queries"]) >= 2


def test_all_v1_skill_prompts_are_progressively_loadable():
    root = Path(__file__).resolve().parents[4] / "config" / "opencode" / "skills"
    names = ["patent-idea-intake", "patent-feature-parser", "patent-search-planner", "patent-evidence-extractor", "patent-inventiveness", "patent-commercial-value", "patent-examiner-opinion", "patent-report-renderer"]
    for name in names:
        content = (root / name / "SKILL.md").read_text(encoding="utf-8")
        assert f"name: {name}" in content


def test_skill_parser_accepts_explanation_followed_by_fenced_json():
    raw = '''根据技能定义，我需要解析技术特征。

```json
{"features": [{"text": "双通道分割", "kind": "necessary", "limitation": "structural"}], "claims": [], "query_terms": ["OCR"]}
```'''
    parsed = _parse_json(raw)
    assert parsed["features"][0]["text"] == "双通道分割"


def test_runner_injects_one_skill_and_forbids_tool_calls():
    prompt = _build_skill_prompt("patent-search-planner", {"query_terms": ["OCR"]})
    assert "<skill name=\"patent-search-planner\">" in prompt
    assert "不得调用任何工具" in prompt
    assert "不得写文件" in prompt


@pytest.mark.asyncio
async def test_opencode_runner_uses_pure_mode_and_reports_tool_only_failure():
    async def fake_run_task(*args, **kwargs):
        assert kwargs["pure"] is True
        yield {"type": "log", "part": {"tool": "write"}}
        yield {"type": "done", "result": ""}

    with pytest.raises(RuntimeError, match=r"attempted tools: write"):
        await OpenCodeSkillRunner(task_runner=fake_run_task).run("patent-search-planner", {"query_terms": ["OCR"]})


class _DeepSeekStyleFeatureRunner(SkillRunner):
    async def run(self, skill_name, payload):
        assert skill_name == "patent-feature-parser"
        return {
            "features": [
                {"text": "将图像拆分为两个并行区域", "kind": "essential", "limitation": True},
                {"text": "以标准化向量记录层级", "kind": "complementary", "limitation": False},
            ],
            "claims": ["一种图像处理方法", "根据权利要求1所述的方法"],
            "query_terms": {"zh": ["双通道分割", "层级向量"], "en": ["dual-channel segmentation"]},
        }


@pytest.mark.asyncio
async def test_feature_step_normalizes_deepseek_style_schema():
    state = PatentCaseState(
        case=CaseMeta(id="feature-schema-001", status=CaseStatus.INTAKE_PARSED),
        request=CaseRequest(idea="一个测试方案"),
        mode="standard",
        invention={},
    )
    state = await FeatureExtractionStep(_DeepSeekStyleFeatureRunner()).run(state)
    assert [(item.kind, item.limitation) for item in state.features] == [
        ("necessary", "functional"), ("optional", "functional"),
    ]
    assert state.invention["query_terms"] == ["双通道分割", "层级向量", "dual-channel segmentation"]
    assert state.claims[0]["type"] == "independent"


def test_missing_priority_date_leaves_novelty_unassessed():
    state = PatentCaseState(
        case=CaseMeta(id="no-priority-001", status=CaseStatus.EVIDENCE_EXTRACTED),
        request=CaseRequest(idea="一个测试方案"),
        mode="standard",
        invention={},
        features=[Feature(id="F-001", text="双通道分割", kind="necessary")],
        documents=[PriorArtDocument(id="DOC-001", type="patent", publication_date="2020-01-01")],
        evidence=[EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            location_type="claim", claim_number="1", feature_ids=["F-001"],
            quoted_text="双通道分割", verified=True, verification_method="source-fetch",
        )],
    )
    result = evaluate_novelty(state.features, state.documents, state.evidence, state.priority_date)
    assert result.overall == "uncertain"


class _ToolOnlyPlannerRunner(SkillRunner):
    async def run(self, skill_name, payload):
        assert skill_name == "patent-search-planner"
        raise RuntimeError("Skill `patent-search-planner` returned no valid textual JSON; attempted tools: write")


@pytest.mark.asyncio
async def test_search_planning_falls_back_when_model_uses_tools_instead_of_json():
    state = PatentCaseState(
        case=CaseMeta(id="planner-fallback-001", status=CaseStatus.FEATURES_EXTRACTED),
        request=CaseRequest(idea="一个测试方案"), mode="standard", invention={"query_terms": ["OCR", "table"]},
        features=[Feature(id="F-001", text="双通道分割", kind="necessary")],
    )
    state = await SearchPlanningStep(_ToolOnlyPlannerRunner()).run(state)
    assert len(state.queries) == 2
    assert state.queries[0].query_text == "OCR table"
    assert state.invention["skill_fallbacks"][0]["step"] == "search_planning"
