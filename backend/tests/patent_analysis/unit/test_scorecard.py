from backend.patent_analysis.domain.models import (
    CaseMeta, CaseRequest, CaseStatus, Feature, PatentCaseState,
)
from backend.patent_analysis.services.scorecard import build_idea_scorecard


def test_scorecard_marks_missing_priority_date_as_unavailable_not_low_innovation():
    state = PatentCaseState(
        case=CaseMeta(id="case-score", status=CaseStatus.INVENTIVENESS_EVALUATED),
        request=CaseRequest(idea="OCR 编码器和解码器生成缩进深度向量"),
        mode="standard",
        features=[Feature(id="F-001", text="独立卷积编码器生成缩进深度向量", kind="necessary")],
    )
    scorecard = build_idea_scorecard(state)
    assert scorecard.innovation.score == 0
    assert scorecard.innovation.status == "unavailable"
    assert scorecard.market_value.score == 0
    assert scorecard.infringement_evidence_availability.score == 1
    assert scorecard.avoidability.score == 2
