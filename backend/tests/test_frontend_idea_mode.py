from pathlib import Path


def test_idea_page_keeps_legacy_default_and_gates_structured_mode():
    page = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(encoding="utf-8")

    assert '<option value="legacy">原 Skill（默认）</option>' in page
    assert 'IDEA_STRUCTURED_BETA_ENABLED' not in page
    assert "structuredIdeaBetaEnabled" in page
    assert '"/api/cases"' in page
    assert '"/api/cases/" + encodeURIComponent(s.caseId) + "/events"' in page
