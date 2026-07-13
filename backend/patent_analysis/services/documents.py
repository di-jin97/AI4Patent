"""Document normalization, deduplication, and ranking.

按 design doc Section 7.1-7.2 定义。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from ..domain.models import PriorArtDocument, RankingResult


def normalize_url(url: str) -> str:
    """规范化 URL：去除尾部斜杠、fragment、tracking params"""
    if not url:
        return ""
    parsed = url.strip().rstrip("/")

    if "#" in parsed:
        parsed = parsed.split("#")[0]

    import urllib.parse as urlparse

    if "?" in parsed:
        base, qs = parsed.split("?", 1)
        params = urlparse.parse_qsl(qs, keep_blank_values=True)
        filtered = [(k, v) for k, v in params
                     if k.lower() not in ("utm_source", "utm_medium", "utm_campaign",
                                           "utm_term", "utm_content", "fbclid",
                                           "gclid", "mc_cid", "mc_eid", "ref")]
        if filtered:
            parsed = base + "?" + urlparse.urlencode(filtered)
        else:
            parsed = base

    return parsed


def normalize_patent_number(raw: str | None) -> str | None:
    """规范化专利号: 去空格、去逗号、大写"""
    if not raw:
        return None
    cleaned = raw.strip().upper()
    cleaned = re.sub(r"[\s,]", "", cleaned)
    return cleaned or None


def generate_document_hash(doc: PriorArtDocument) -> str:
    """为文档生成内容 hash"""
    raw = (
        (doc.title or "")
        + (doc.abstract or "")
        + (doc.claims_text or "")
        + (doc.description_snippet or "")
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def deduplicate_documents(docs: list[PriorArtDocument]) -> list[PriorArtDocument]:
    """去重: 按 publication_number > normalized_url > content_hash 顺序"""
    seen_pn: set[str] = set()
    seen_url: set[str] = set()
    seen_hash: set[str] = set()
    result: list[PriorArtDocument] = []

    for doc in docs:
        pn = normalize_patent_number(doc.publication_number)
        url = normalize_url(doc.source_url or doc.normalized_url or "")
        content_hash = doc.content_hash or generate_document_hash(doc)

        if pn and pn in seen_pn:
            continue
        if url and url in seen_url:
            continue

        has_real_content = bool(doc.title or doc.abstract or doc.claims_text or doc.description_snippet)
        if content_hash and has_real_content and content_hash in seen_hash:
            continue

        if pn:
            seen_pn.add(pn)
        if url:
            seen_url.add(url)
        if content_hash and has_real_content:
            seen_hash.add(content_hash)

        result.append(doc)

    return result


def rank_documents(
    docs: list[PriorArtDocument],
    features: list[str],
    problem_description: str = "",
    priority_date: str | None = None,
    weights: dict[str, float] | None = None,
) -> list[RankingResult]:
    """基于特征覆盖和相似度对文献排序.
    权重可按模式配置版本化 (design doc 7.2)
    """
    w = weights or {
        "featureCoverage": 0.30,
        "fieldSimilarity": 0.15,
        "problemSimilarity": 0.15,
        "claimSimilarity": 0.15,
        "classificationSimilarity": 0.08,
        "citationSignal": 0.05,
        "sourceReliability": 0.07,
        "dateValidity": 0.05,
    }

    results = []
    for doc in docs:
        feature_coverage = _estimate_feature_coverage(doc, features)
        field_similarity = 0.5
        problem_similarity = 0.3
        claim_similarity = 0.3
        classification_similarity = 0.1
        citation_signal = 0.0
        source_reliability = 0.8 if doc.type == "patent" else 0.5
        date_validity = 1.0
        duplicate_risk = 0.0

        base_score = (
            w["featureCoverage"] * feature_coverage
            + w["fieldSimilarity"] * field_similarity
            + w["problemSimilarity"] * problem_similarity
            + w["claimSimilarity"] * claim_similarity
            + w["classificationSimilarity"] * classification_similarity
            + w["citationSignal"] * citation_signal
            + w["sourceReliability"] * source_reliability
            + w["dateValidity"] * date_validity
        )

        novelty_score = base_score + 0.15 * feature_coverage
        d1_score = base_score + 0.10 * problem_similarity + 0.10 * feature_coverage
        d2_score = base_score + 0.05 * feature_coverage

        fetch_priority = (
            0.45 * max(novelty_score, d1_score, d2_score)
            + 0.35 * (1.0 - feature_coverage)
            + 0.20 * 0.8
        )

        results.append(RankingResult(
            document_id=doc.id,
            base_score=base_score,
            feature_coverage=feature_coverage,
            field_similarity=field_similarity,
            problem_similarity=problem_similarity,
            claim_similarity=claim_similarity,
            classification_similarity=classification_similarity,
            citation_signal=citation_signal,
            source_reliability=source_reliability,
            date_validity=date_validity,
            duplicate_risk=duplicate_risk,
            novelty_score=novelty_score,
            d1_score=d1_score,
            d2_score=d2_score,
            fetch_priority=fetch_priority,
        ))

    results.sort(key=lambda r: r.fetch_priority, reverse=True)
    return results


def _estimate_feature_coverage(doc: PriorArtDocument, features: list[str]) -> float:
    """简单特征覆盖估算: 按关键词匹配"""
    if not features:
        return 0.0

    text = (
        (doc.title or "")
        + " "
        + (doc.abstract or "")
        + " "
        + (doc.claims_text or "")
        + " "
        + (doc.description_snippet or "")
    ).lower()

    matched = 0
    for feature in features:
        keywords = feature.lower().split()
        if any(kw in text for kw in keywords):
            matched += 1

    return matched / len(features)


def build_patent_google_url(patent_number: str) -> str:
    """根据专利号拼接 Google Patents URL"""
    cleaned = normalize_patent_number(patent_number)
    if not cleaned:
        return ""
    return f"https://patents.google.com/patent/{cleaned}/en"
