"""Evidence extraction service.

按 design doc Section 7.3 定义：从文献和全文记录中提取可定位证据。
证据必须具有有效定位、原文引用和特征关联。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from ..domain.ids import IDGenerator
from ..domain.models import (
    EvidenceItem,
    PriorArtDocument,
    FullTextRecord,
    PatentCaseState,
)
from ..domain.validation import EvidenceValidator


def extract_evidence(
    state: PatentCaseState,
    document_id: str,
    source_type: str,
    source_url: str | None,
    location_type: str | None,
    claim_number: str | None,
    paragraph_range: str | None,
    page_range: str | None,
    section: str | None,
    quoted_text: str,
    normalized_meaning: str,
    feature_ids: list[str],
    supports: list[str],
    confidence: float,
    verified: bool = False,
    verification_method: str | None = None,
) -> EvidenceItem:
    gen = IDGenerator()
    for ev in state.evidence:
        gen.next("EV")

    ev_id = gen.next("EV")

    full_text = next(
        (ft for ft in state.full_text if ft.document_id == document_id),
        None,
    )
    doc_version = full_text.content_hash if full_text else ""

    return EvidenceItem(
        id=ev_id,
        document_id=document_id,
        document_version=doc_version,
        source_type=source_type,
        source_url=source_url,
        location_type=location_type,
        claim_number=claim_number,
        paragraph_range=paragraph_range,
        page_range=page_range,
        section=section,
        quoted_text=quoted_text,
        normalized_meaning=normalized_meaning,
        feature_ids=feature_ids,
        supports=supports,
        confidence=confidence,
        verified=verified,
        verification_method=verification_method,
    )


def validate_evidence_list(
    evidence_list: list[EvidenceItem],
    require_location: bool = True,
) -> list[EvidenceItem]:
    """验证证据列表，返回通过验证的有效证据"""
    validator = EvidenceValidator()
    return [
        ev for ev in evidence_list
        if len(validator.validate(ev, require_location=require_location)) == 0
    ]


def build_feature_evidence_map(
    evidence_list: list[EvidenceItem],
) -> dict[str, list[str]]:
    """构建 特征ID → 证据ID列表 的映射"""
    mapping: dict[str, list[str]] = {}
    for ev in evidence_list:
        for fid in ev.feature_ids:
            if fid not in mapping:
                mapping[fid] = []
            mapping[fid].append(ev.id)
    return mapping


def build_document_feature_coverage_matrix(
    evidence_list: list[EvidenceItem],
    feature_ids: list[str],
) -> dict[str, dict[str, str]]:
    """构建 文献ID → 特征ID → 覆盖状态 的矩阵"""
    matrix: dict[str, dict[str, str]] = {}
    doc_features: dict[str, set[str]] = {}

    for ev in evidence_list:
        if ev.document_id not in doc_features:
            doc_features[ev.document_id] = set()
        for fid in ev.feature_ids:
            if fid in feature_ids:
                doc_features[ev.document_id].add(fid)

    for doc_id, covered in doc_features.items():
        matrix[doc_id] = {}
        for fid in feature_ids:
            if fid in covered:
                matrix[doc_id][fid] = "yes"
            else:
                matrix[doc_id][fid] = "no"

    return matrix
