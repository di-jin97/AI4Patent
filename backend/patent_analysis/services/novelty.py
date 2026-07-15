"""Novelty evaluation engine.

按 design doc Section 7.3 定义：单一文献、全部必要特征、直接无歧义公开、
日期有效、证据完整。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..domain.models import (
    EvidenceItem,
    Feature,
    NoveltyEvaluationResult,
    PriorArtDocument,
)
from ..domain.dates import is_valid_prior_art


def evaluate_novelty(
    features: list[Feature],
    documents: list[PriorArtDocument],
    evidence: list[EvidenceItem],
    priority_date: str | None = None,
) -> NoveltyEvaluationResult:
    """评估新颖性。返回每文献的特征覆盖矩阵和整体结论。

    规则:
    - 单一文献 + 全部必要特征 + 直接无歧义公开 + 日期有效 + 证据完整 = not-novel
    - 任何文献不满足上述条件 = novel
    - 证据不足或无有效文献 = uncertain
    """
    necessary_features = [f for f in features if f.kind == "necessary"]
    necessary_ids = [f.id for f in necessary_features]
    all_feature_ids = [f.id for f in features]

    ev_by_doc: dict[str, list[EvidenceItem]] = {}
    for ev in evidence:
        if ev.verified or ev.has_location():
            ev_by_doc.setdefault(ev.document_id, []).append(ev)

    by_document: list[dict[str, Any]] = []
    any_not_novel = False
    all_evidence_ids: list[str] = []

    for doc in documents:
        doc_evs = ev_by_doc.get(doc.id, [])
        coverage: dict[str, str] = {}
        doc_evidence_ids: list[str] = []

        for fid in all_feature_ids:
            covered = any(fid in ev.feature_ids for ev in doc_evs)
            coverage[fid] = "yes" if covered else "no"

        for fid in necessary_ids:
            covered = coverage.get(fid, "no") == "yes"
            if not covered:
                break
        else:
            if not priority_date:
                # A matching document is useful retrieval evidence, but without
                # a user-supplied priority date it cannot support a legal
                # novelty conclusion.  Do not silently treat every document as
                # pre-priority prior art.
                coverage["_date_valid"] = "unassessed"
                coverage["_complete"] = "unassessed"
                doc_evidence_ids = [ev.id for ev in doc_evs]
                all_evidence_ids.extend(doc_evidence_ids)
            elif not is_valid_prior_art(doc.publication_date, priority_date):
                coverage["_date_valid"] = "no"
            else:
                doc_evidence_ids = [ev.id for ev in doc_evs]
                all_evidence_ids.extend(doc_evidence_ids)

                is_not_novel = True
                is_complete = all(coverage.get(fid, "no") == "yes" for fid in necessary_ids)

                if is_complete:
                    coverage["_complete"] = "yes"
                    any_not_novel = True
                else:
                    coverage["_complete"] = "partial"

        by_document.append({
            "document_id": doc.id,
            "feature_coverage": coverage,
            "conclusion": "not-novel" if coverage.get("_complete") == "yes" else "uncertain",
            "evidence_ids": doc_evidence_ids,
        })

    if not priority_date and documents:
        overall = "uncertain"
    elif any_not_novel:
        overall = "not-novel"
    elif not by_document and not documents:
        overall = "novel"
    elif not by_document:
        overall = "uncertain"
    else:
        overall = "novel"

    return NoveltyEvaluationResult(
        by_document=by_document,
        overall=overall,
        evidence_ids=all_evidence_ids,
    )
