from pathlib import Path


def test_idea_page_uses_structured_v1_by_default_and_keeps_legacy_rollback():
    page = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")

    assert '<option value="structured" selected>结构化 IDEA 评审 1.0（默认）</option>' in page
    assert '<option value="legacy">原 Skill（回滚）</option>' in page
    assert 'IDEA_STRUCTURED_BETA_ENABLED' not in page
    assert "structuredIdeaBetaEnabled" in page
    assert '"/api/cases"' in page
    assert '"/api/cases/" + encodeURIComponent(s.caseId) + "/events"' in page
