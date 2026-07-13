"""Unit tests for evidence extraction, novelty evaluation, quality gate.

按 design doc Section 12.1 定义。
"""

import pytest

from backend.patent_analysis.domain.models import (
    PatentCaseState, CaseMeta, CaseRequest, CaseStatus,
    Feature, PriorArtDocument, EvidenceItem, FullTextRecord,
    ExecutionBudget,
)
from backend.patent_analysis.services.evidence import (
    extract_evidence,
    validate_evidence_list,
    build_feature_evidence_map,
    build_document_feature_coverage_matrix,
)
from backend.patent_analysis.services.novelty import evaluate_novelty
from backend.patent_analysis.services.quality import run_quality_gate


def _make_state(features=None, documents=None, evidence=None, priority_date=None, full_text=None):
    return PatentCaseState(
        case=CaseMeta(id="case-test", status=CaseStatus.EVIDENCE_EXTRACTED),
        request=CaseRequest(idea="A test idea"),
        mode="standard",
        features=features or [],
        documents=documents or [],
        evidence=evidence or [],
        full_text=full_text or [],
        priority_date=priority_date,
        budget=ExecutionBudget(),
    )


# ─── Evidence Extraction ─────────────────────────────────────────────

class TestEvidenceExtraction:
    def test_extract_creates_valid_evidence(self):
        state = _make_state(
            full_text=[
                FullTextRecord(
                    document_id="DOC-001", content_hash="abc123",
                    url="https://example.com", fetched_at="2026-01-01T00:00:00Z",
                ),
            ],
        )
        ev = extract_evidence(
            state=state,
            document_id="DOC-001",
            source_type="patent",
            source_url="https://example.com/patent1",
            location_type="claim",
            claim_number="1",
            paragraph_range=None,
            page_range=None,
            section=None,
            quoted_text="A method comprising step A and step B.",
            normalized_meaning="method with steps A and B",
            feature_ids=["F-001"],
            supports=["novelty:DOC-001:F-001"],
            confidence=0.92,
            verified=True,
            verification_method="source-fetch",
        )
        assert ev.id == "EV-001"
        assert ev.document_id == "DOC-001"
        assert ev.document_version == "abc123"
        assert ev.feature_ids == ["F-001"]
        assert ev.verified is True

    def test_sequential_ids(self):
        state = _make_state()
        ev1 = extract_evidence(
            state, "DOC-001", "patent", None, "claim", "1", None, None, None,
            "text1", "meaning1", ["F-001"], [], 0.9, False, None,
        )
        state.evidence.append(ev1)
        ev2 = extract_evidence(
            state, "DOC-001", "patent", None, "claim", "2", None, None, None,
            "text2", "meaning2", ["F-002"], [], 0.9, False, None,
        )
        assert ev1.id == "EV-001"
        assert ev2.id == "EV-002"


class TestValidateEvidenceList:
    def test_valid_evidence_passes(self):
        ev = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            source_url="https://example.com", location_type="claim",
            claim_number="1", quoted_text="text", verified=True,
            verification_method="source-fetch", confidence=0.9,
        )
        valid = validate_evidence_list([ev], require_location=True)
        assert len(valid) == 1

    def test_no_location_fails(self):
        ev = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            quoted_text="text", verified=True, confidence=0.5,
        )
        valid = validate_evidence_list([ev], require_location=True)
        assert len(valid) == 0


class TestBuildFeatureEvidenceMap:
    def test_correct_mapping(self):
        ev1 = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            feature_ids=["F-001", "F-002"],
        )
        ev2 = EvidenceItem(
            id="EV-002", document_id="DOC-001", source_type="patent",
            feature_ids=["F-001"],
        )
        mapping = build_feature_evidence_map([ev1, ev2])
        assert mapping["F-001"] == ["EV-001", "EV-002"]
        assert mapping["F-002"] == ["EV-001"]


class TestBuildCoverageMatrix:
    def test_matrix(self):
        ev = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            feature_ids=["F-001"],
        )
        matrix = build_document_feature_coverage_matrix(
            [ev], ["F-001", "F-002"]
        )
        assert matrix["DOC-001"]["F-001"] == "yes"
        assert matrix["DOC-001"]["F-002"] == "no"


# ─── Novelty Engine ──────────────────────────────────────────────────

class TestNoveltyEngine:
    def test_novel_when_no_docs(self):
        state = _make_state(
            features=[Feature(id="F-001", text="cache", kind="necessary")],
        )
        result = evaluate_novelty(
            state.features, state.documents, state.evidence, state.priority_date
        )
        assert result.overall == "novel"

    def test_not_novel_when_fully_covered(self):
        doc = PriorArtDocument(
            id="DOC-001", type="patent",
            publication_date="2020-01-01",
        )
        ev = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            source_url="https://example.com", location_type="claim",
            claim_number="1", quoted_text="cache method", verified=True,
            verification_method="source-fetch", confidence=0.9,
            feature_ids=["F-001"],
        )
        result = evaluate_novelty(
            features=[Feature(id="F-001", text="cache", kind="necessary")],
            documents=[doc],
            evidence=[ev],
            priority_date="2023-01-01",
        )
        assert result.overall == "not-novel"

    def test_novel_when_feature_not_covered(self):
        doc = PriorArtDocument(
            id="DOC-001", type="patent",
            publication_date="2020-01-01",
        )
        ev = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            source_url="https://example.com", location_type="claim",
            claim_number="1", quoted_text="other method", verified=True,
            verification_method="source-fetch", confidence=0.9,
            feature_ids=["F-002"],
        )
        result = evaluate_novelty(
            features=[Feature(id="F-001", text="cache", kind="necessary")],
            documents=[doc],
            evidence=[ev],
            priority_date="2023-01-01",
        )
        assert result.overall == "novel"

    def test_post_priority_doc_not_counted(self):
        doc = PriorArtDocument(
            id="DOC-001", type="patent",
            publication_date="2025-01-01",  # after priority
        )
        ev = EvidenceItem(
            id="EV-001", document_id="DOC-001", source_type="patent",
            source_url="https://example.com", location_type="claim",
            claim_number="1", quoted_text="cache method", verified=True,
            verification_method="source-fetch", confidence=0.9,
            feature_ids=["F-001"],
        )
        result = evaluate_novelty(
            features=[Feature(id="F-001", text="cache", kind="necessary")],
            documents=[doc],
            evidence=[ev],
            priority_date="2023-01-01",
        )
        assert result.overall == "novel"


# ─── Quality Gate ────────────────────────────────────────────────────

class TestQualityGate:
    def test_pass_with_valid_state(self):
        state = _make_state(
            features=[Feature(id="F-001", text="cache", kind="necessary")],
            documents=[
                PriorArtDocument(
                    id="DOC-001", type="patent",
                    publication_date="2020-01-01",
                ),
            ],
            evidence=[
                EvidenceItem(
                    id="EV-001", document_id="DOC-001", source_type="patent",
                    source_url="https://example.com", location_type="claim",
                    claim_number="1", quoted_text="cache method", verified=True,
                    verification_method="source-fetch", confidence=0.9,
                    feature_ids=["F-001"],
                ),
            ],
            priority_date="2023-01-01",
        )
        result = run_quality_gate(state)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_error_unverified_evidence(self):
        state = _make_state(
            evidence=[
                EvidenceItem(
                    id="EV-001", document_id="DOC-001", source_type="patent",
                    verified=True, verification_method=None,
                ),
            ],
        )
        result = run_quality_gate(state)
        codes = {e["code"] for e in result.errors}
        assert "EVIDENCE_NO_VERIFICATION_METHOD" in codes

    def test_error_post_priority_document(self):
        state = _make_state(
            features=[Feature(id="F-001", text="cache", kind="necessary")],
            documents=[
                PriorArtDocument(
                    id="DOC-001", type="patent",
                    publication_date="2025-01-01",
                ),
            ],
            evidence=[
                EvidenceItem(
                    id="EV-001", document_id="DOC-001", source_type="patent",
                    source_url="https://example.com", location_type="claim",
                    claim_number="1", quoted_text="method", verified=True,
                    verification_method="source-fetch", confidence=0.9,
                    feature_ids=["F-001"],
                ),
            ],
            priority_date="2023-01-01",
        )
        result = run_quality_gate(state)
        codes = {e["code"] for e in result.errors}
        assert "DATE_POST_PRIORITY" in codes
