"""Golden baseline fixture data for patent analysis.

按 design doc Section 12.1 Golden Cases 定义:
- 单篇完整覆盖
- 多文献分别覆盖  
- D1+D2 有结合启示
- D2 无结合动机
- 跨领域迁移
- 晚公开日
- 全文缺失
- Exa 家族重复
- Evidence 无定位
- 预算耗尽
- 一句模糊 Idea
- 云端算法低可取证性

Fixture 不含真实用户 Idea/密钥，全部使用合成或公开材料。
"""

from __future__ import annotations

from backend.patent_analysis.domain.models import (
    CaseMeta, CaseRequest, CaseStatus, PatentCaseState,
    Feature, PriorArtDocument, EvidenceItem, FullTextRecord,
    ExecutionBudget, RankingResult, InventiveStepRoute, InventiveStepResult,
    NoveltyEvaluationResult, QualityGateResult,
)
from backend.patent_analysis.services.evidence import build_document_feature_coverage_matrix
from backend.patent_analysis.services.novelty import evaluate_novelty
from backend.patent_analysis.services.quality import run_quality_gate


def build_state(
    case_id: str,
    mode: str = "standard",
    features: list[Feature] | None = None,
    documents: list[PriorArtDocument] | None = None,
    evidence: list[EvidenceItem] | None = None,
    priority_date: str | None = "2023-06-01",
) -> PatentCaseState:
    return PatentCaseState(
        case=CaseMeta(id=case_id, status=CaseStatus.EVIDENCE_EXTRACTED, revision=5),
        request=CaseRequest(idea="A dynamic cache tier management system"),
        mode=mode,
        jurisdiction=["CN"],
        priority_date=priority_date,
        features=features or [],
        documents=documents or [],
        evidence=evidence or [],
        budget=ExecutionBudget(),
    )


# ─── 1. 单篇完整覆盖 ──────────────────────────────────────────────────

def golden_single_doc_full_coverage() -> PatentCaseState:
    """DOC-001 单篇公开所有必要特征 — 新颖性应判定为 not-novel"""
    return build_state(
        case_id="golden-001",
        features=[
            Feature(id="F-001", text="依据工作负载动态调整缓存分层", kind="necessary"),
            Feature(id="F-002", text="基于访问频率选择淘汰策略", kind="necessary"),
            Feature(id="F-003", text="使用机器学习预测缓存命中率", kind="optional"),
        ],
        documents=[
            PriorArtDocument(
                id="DOC-001", type="patent",
                publication_number="CN102063547B",
                title="Dynamic cache tier management",
                abstract="A method for dynamically adjusting cache tiers based on workload",
                publication_date="2011-05-18",
            ),
        ],
        evidence=[
            EvidenceItem(
                id="EV-001", document_id="DOC-001",
                document_version="sha256:abc123",
                source_type="patent",
                source_url="https://patents.google.com/patent/CN102063547B/en",
                location_type="claim", claim_number="1",
                quoted_text="dynamically adjusting cache tiers based on workload characteristics",
                normalized_meaning="动态调整缓存分层",
                feature_ids=["F-001", "F-002"],
                supports=["novelty:DOC-001:F-001"],
                confidence=0.95, verified=True,
                verification_method="source-fetch",
            ),
        ],
    )


# ─── 2. 多文献分别覆盖 ────────────────────────────────────────────────

def golden_multi_doc_partial_coverage() -> PatentCaseState:
    """DOC-001 和 DOC-002 分别覆盖不同特征 — 新颖性应判定为 novel"""
    return build_state(
        case_id="golden-002",
        features=[
            Feature(id="F-001", text="特征A", kind="necessary"),
            Feature(id="F-002", text="特征B", kind="necessary"),
        ],
        documents=[
            PriorArtDocument(
                id="DOC-001", type="patent",
                publication_date="2020-01-01",
            ),
            PriorArtDocument(
                id="DOC-002", type="patent",
                publication_date="2020-06-01",
            ),
        ],
        evidence=[
            EvidenceItem(
                id="EV-001", document_id="DOC-001",
                source_type="patent",
                source_url="https://example.com/doc1",
                location_type="claim", claim_number="1",
                quoted_text="feature A implementation",
                feature_ids=["F-001"],
                verified=True, verification_method="source-fetch",
                confidence=0.9,
            ),
            EvidenceItem(
                id="EV-002", document_id="DOC-002",
                source_type="patent",
                source_url="https://example.com/doc2",
                location_type="claim", claim_number="1",
                quoted_text="feature B implementation",
                feature_ids=["F-002"],
                verified=True, verification_method="source-fetch",
                confidence=0.9,
            ),
        ],
    )


# ─── 3. D1+D2 有结合启示 ──────────────────────────────────────────────

def golden_d1_d2_with_motivation() -> PatentCaseState:
    """D1+D2 有明确技术启示 — 创造性应判定为 not-inventive"""
    state = build_state(
        case_id="golden-003",
        features=[
            Feature(id="F-001", text="D1公开的特征A", kind="necessary"),
            Feature(id="F-002", text="区别特征B(D2公开)", kind="necessary"),
        ],
        documents=[
            PriorArtDocument(
                id="DOC-001", type="patent",
                publication_date="2020-01-01",
                title="D1 closest prior art",
            ),
            PriorArtDocument(
                id="DOC-002", type="patent",
                publication_date="2021-03-01",
                title="D2 teaching motivation",
            ),
        ],
        evidence=[
            EvidenceItem(
                id="EV-001", document_id="DOC-001",
                source_type="patent",
                source_url="https://example.com/d1",
                location_type="claim", claim_number="1",
                quoted_text="D1 feature A... also suggests combining with...",
                feature_ids=["F-001"],
                supports=["ROUTE-001:d1"],
                verified=True, verification_method="source-fetch",
                confidence=0.9,
            ),
            EvidenceItem(
                id="EV-002", document_id="DOC-002",
                source_type="patent",
                source_url="https://example.com/d2",
                location_type="paragraph", paragraph_range="[0023]-[0025]",
                quoted_text="explicitly teaches combining B with A to achieve...",
                feature_ids=["F-002"],
                supports=["ROUTE-001:d2", "ROUTE-001:motivation"],
                verified=True, verification_method="source-fetch",
                confidence=0.95,
            ),
        ],
    )
    state.inventiveness = InventiveStepResult(
        routes=[
            InventiveStepRoute(
                id="ROUTE-001",
                d1_document_id="DOC-001",
                difference_feature_ids=["F-002"],
                actual_technical_problem="如何实现特征B",
                d2_document_ids=["DOC-002"],
                motivation_evidence_ids=["EV-002"],
                obstacle_evidence_ids=[],
                synergy_evidence_ids=[],
                conclusion="not-inventive",
            ),
        ],
        strongest_route_id="ROUTE-001",
        overall="not-inventive",
    )
    return state


# ─── 4. D2 无结合动机 ──────────────────────────────────────────────────

def golden_d2_no_motivation() -> PatentCaseState:
    """D2 公开了特征但无结合启示 — 创造性应判定为 inventive"""
    state = build_state(
        case_id="golden-004",
        features=[
            Feature(id="F-001", text="特征A", kind="necessary"),
            Feature(id="F-002", text="特征B(D2中公开)", kind="necessary"),
        ],
        documents=[
            PriorArtDocument(id="DOC-001", type="patent", publication_date="2020-01-01"),
            PriorArtDocument(id="DOC-002", type="patent", publication_date="2021-01-01"),
        ],
        evidence=[
            EvidenceItem(
                id="EV-001", document_id="DOC-001",
                source_type="patent",
                source_url="https://example.com/d1",
                location_type="claim", claim_number="1",
                quoted_text="feature A", feature_ids=["F-001"],
                verified=True, verification_method="source-fetch", confidence=0.9,
            ),
            EvidenceItem(
                id="EV-002", document_id="DOC-002",
                source_type="patent",
                source_url="https://example.com/d2",
                location_type="paragraph", paragraph_range="[0010]",
                quoted_text="feature B in unrelated field", feature_ids=["F-002"],
                verified=True, verification_method="source-fetch", confidence=0.8,
            ),
        ],
    )
    state.inventiveness = InventiveStepResult(
        routes=[
            InventiveStepRoute(
                id="ROUTE-001",
                d1_document_id="DOC-001",
                difference_feature_ids=["F-002"],
                actual_technical_problem="提高缓存效率",
                d2_document_ids=["DOC-002"],
                motivation_evidence_ids=[],
                obstacle_evidence_ids=[],
                synergy_evidence_ids=[],
                conclusion="inventive",
            ),
        ],
        strongest_route_id="ROUTE-001",
        overall="inventive",
    )
    return state


# ─── 5. 晚公开日 ───────────────────────────────────────────────────────

def golden_late_publication_date() -> PatentCaseState:
    """文献公开日晚于 priority_date — 不应作为现有技术"""
    return build_state(
        case_id="golden-005",
        features=[
            Feature(id="F-001", text="动态缓存", kind="necessary"),
        ],
        priority_date="2023-01-01",
        documents=[
            PriorArtDocument(
                id="DOC-001", type="patent",
                publication_date="2025-06-01",  # after priority
            ),
        ],
        evidence=[
            EvidenceItem(
                id="EV-001", document_id="DOC-001",
                source_type="patent",
                source_url="https://example.com/late",
                location_type="claim", claim_number="1",
                quoted_text="dynamic cache feature",
                feature_ids=["F-001"],
                verified=True, verification_method="source-fetch",
                confidence=0.9,
            ),
        ],
    )


# ─── 6. Evidence 无定位 ────────────────────────────────────────────────

def golden_evidence_no_location() -> PatentCaseState:
    """证据有引用但无定位字段 — Quality Gate 应降级"""
    return build_state(
        case_id="golden-006",
        features=[Feature(id="F-001", text="特征A", kind="necessary")],
        documents=[PriorArtDocument(id="DOC-001", type="patent", publication_date="2020-01-01")],
        evidence=[
            EvidenceItem(
                id="EV-001", document_id="DOC-001",
                source_type="patent",
                quoted_text="A method...",
                feature_ids=["F-001"],
                verified=True, verification_method="source-fetch",
                confidence=0.8,
            ),
        ],
    )


# ─── 7. 模糊 Idea ──────────────────────────────────────────────────────

def golden_vague_idea() -> PatentCaseState:
    """一句模糊描述 — 特征提取应保守"""
    return build_state(
        case_id="golden-007",
        mode="quick",
        features=[Feature(id="F-001", text="AI加速", kind="necessary")],
        documents=[],
        evidence=[],
    )


# ─── 8. Golden runner ──────────────────────────────────────────────────

def run_all_golden_scenarios() -> dict[str, dict]:
    """执行所有 Golden 场景并返回结果摘要"""
    scenarios = {
        "single-doc-full-coverage": (golden_single_doc_full_coverage, None),
        "multi-doc-partial": (golden_multi_doc_partial_coverage, None),
        "d1-d2-with-motivation": (golden_d1_d2_with_motivation, None),
        "d2-no-motivation": (golden_d2_no_motivation, None),
        "late-publication-date": (golden_late_publication_date, None),
        "evidence-no-location": (golden_evidence_no_location, None),
        "vague-idea": (golden_vague_idea, None),
    }

    results = {}
    for name, (builder, _) in scenarios.items():
        state = builder()

        novelty_result = evaluate_novelty(
            state.features, state.documents, state.evidence, state.priority_date
        )
        quality_result = run_quality_gate(state)

        results[name] = {
            "case_id": state.case.id,
            "features": [f.id for f in state.features],
            "documents": [d.id for d in state.documents],
            "evidence": [e.id for e in state.evidence],
            "novelty": novelty_result.overall,
            "novelty_by_doc": [
                {"doc": d["document_id"], "conclusion": d["conclusion"]}
                for d in novelty_result.by_document
            ],
            "quality_passed": quality_result.passed,
            "quality_errors": [e["code"] for e in quality_result.errors],
        }

    return results
