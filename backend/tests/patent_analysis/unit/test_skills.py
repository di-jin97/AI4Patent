from pathlib import Path

import pytest

from backend.patent_analysis.skills.runner import RuleBasedSkillRunner


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
