"""Evidence-aware 0--5 IDEA scorecard.

The 1--5 criteria are reused from ``patent-pct-review``.  This workflow adds
0 only for unavailable evidence, so lack of data is never mistaken for a poor
commercial or technical score.
"""

from __future__ import annotations

from ..domain.models import IdeaScoreCard, ScoreCardItem


def build_idea_scorecard(state) -> IdeaScoreCard:
    """Build the report-front scorecard from persisted workflow facts only."""
    innovation = _innovation_score(state)
    implementation_text = " ".join([state.request.idea, *(item.text for item in state.features)]).lower()
    internal_terms = ("算法", "模型", "编码器", "解码器", "卷积", "神经网络", "训练", "推理", "向量", "ocr")
    observable_terms = ("接口", "协议", "坐标", "输出", "外观", "规格", "性能")

    if any(term in implementation_text for term in internal_terms):
        evidence = ScoreCardItem(score=1, status="preliminary", reason="核心限定主要落在编码器、解码器或内部算法层，外部通常难以直接观察或证明。")
        avoidability = ScoreCardItem(score=2, status="preliminary", reason="可替换分割策略、编码器或版面模型通常存在，竞争者可能以较小架构调整绕开。")
    elif any(term in implementation_text for term in observable_terms):
        evidence = ScoreCardItem(score=4, status="preliminary", reason="核心特征可望通过接口行为、输出格式或性能测试观察，但仍需产品样本验证。")
        avoidability = ScoreCardItem(score=3, status="preliminary", reason="存在替代实现路径，但需结合权利要求范围和竞品实现进一步确认代价。")
    else:
        evidence = ScoreCardItem(score=0, status="unavailable", reason="未能从当前保护点确定外部可观测的实现形态，暂不评分。")
        avoidability = ScoreCardItem(score=0, status="unavailable", reason="缺少可验证的替代技术路径或产品实现资料，暂不评分。")

    return IdeaScoreCard(
        innovation=innovation,
        market_value=ScoreCardItem(score=0, status="unavailable", reason="尚未接入市场、产品或竞品采用证据；不以专利文本推断市场价值。"),
        infringement_evidence_availability=evidence,
        avoidability=avoidability,
    )


def _innovation_score(state) -> ScoreCardItem:
    # A priority date is indispensable to an evidence-bound novelty score.
    if not state.priority_date:
        return ScoreCardItem(score=0, status="unavailable", reason="未提供优先权日，无法确认检索文献是否构成有效现有技术。")
    if not state.evidence or not state.novelty:
        return ScoreCardItem(score=0, status="unavailable", reason="尚无经定位和日期校验的对比证据，暂不评分。")
    if state.novelty.overall == "not-novel":
        return ScoreCardItem(score=1, status="verified", reason="存在单篇有效现有技术覆盖全部必要特征，符合 PCT 量表的低创新性情形。")
    if state.inventiveness and state.inventiveness.overall == "not-inventive":
        return ScoreCardItem(score=2, status="verified", reason="虽未被单篇完整公开，但已存在具明确结合动机的 D1/D2 路线。")
    if state.inventiveness and state.inventiveness.overall == "inventive":
        return ScoreCardItem(score=4, status="verified", reason="与最接近技术存在可核验区别特征，当前证据未显示可直接结合的启示。")
    return ScoreCardItem(score=3, status="preliminary", reason="未见单篇完整覆盖，但创造性路线仍需补充检索或结合动机证据。")
