"""Unit tests for domain models, IDs, dates, and validators.

按 design doc Section 12.1 定义单元测试层次。
"""

import json
import pytest
from datetime import date

from backend.patent_analysis.domain.ids import IDGenerator
from backend.patent_analysis.domain.dates import (
    normalize_date,
    parse_date,
    is_before_priority_date,
    is_valid_prior_art,
)
from backend.patent_analysis.domain.models import (
    CaseStatus,
    Feature,
    EvidenceRef,
    EvidenceItem,
    PriorArtDocument,
    ExecutionBudget,
    PatentCaseState,
    CaseMeta,
    CaseRequest,
    InventiveStepRoute,
    NoveltyEvaluationResult,
    QualityGateResult,
)
from backend.patent_analysis.domain.validation import (
    EvidenceValidator,
    DateValidator,
    FeatureCoverageValidator,
    QualityGate,
)


# ─── ID Generation ────────────────────────────────────────────────────

class TestIDGenerator:
    def test_sequential_f_ids(self):
        gen = IDGenerator()
        assert gen.next("F") == "F-001"
        assert gen.next("F") == "F-002"
        assert gen.next("FEATURE") == "F-003"

    def test_sequential_doc_ids(self):
        gen = IDGenerator()
        assert gen.next("DOC") == "DOC-001"
        assert gen.next("DOCUMENT") == "DOC-002"

    def test_mixed_type_ids(self):
        gen = IDGenerator()
        assert gen.next("F") == "F-001"
        assert gen.next("DOC") == "DOC-001"
        assert gen.next("EV") == "EV-001"
        assert gen.next("F") == "F-002"
        assert gen.next("ROUTE") == "ROUTE-001"
        assert gen.next("Q") == "Q-001"

    def test_current_counter(self):
        gen = IDGenerator()
        assert gen.current("F") == 0
        gen.next("F")
        assert gen.current("F") == 1

    def test_reset(self):
        gen = IDGenerator()
        gen.next("F")
        gen.reset()
        assert gen.current("F") == 0


# ─── Date Parsing ─────────────────────────────────────────────────────

class TestNormalizeDate:
    def test_iso_date(self):
        assert normalize_date("2023-06-15") == "2023-06-15"
        assert normalize_date("2021-01-01") == "2021-01-01"

    def test_yymmdd(self):
        assert normalize_date("2023年3月5日") == "2023-03-05"
        assert normalize_date("2023/03/05") == "2023-03-05"

    def test_none_or_empty(self):
        assert normalize_date(None) is None
        assert normalize_date("") is None
        assert normalize_date("  ") is None

    def test_invalid(self):
        assert normalize_date("not a date") is None
        assert normalize_date("9999-99-99") is None


class TestParseDate:
    def test_valid(self):
        d = parse_date("2023-06-15")
        assert d == date(2023, 6, 15)

    def test_none(self):
        assert parse_date(None) is None

    def test_invalid(self):
        assert parse_date("hello") is None


class TestPriorityDate:
    def test_is_before(self):
        assert is_before_priority_date("2020-01-01", "2023-01-01")
        assert not is_before_priority_date("2023-01-01", "2023-01-01")

    def test_is_not_before(self):
        assert not is_before_priority_date("2025-01-01", "2023-01-01")

    def test_valid_prior_art(self):
        assert is_valid_prior_art("2020-01-01", "2023-01-01")
        assert is_valid_prior_art("2023-01-01", "2023-01-01")
        assert not is_valid_prior_art("2025-01-01", "2023-01-01")
        assert not is_valid_prior_art(None, "2023-01-01")


# ─── Evidence Validation ──────────────────────────────────────────────

class TestEvidenceValidator:
    def test_valid_evidence(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            source_url="https://example.com",
            location_type="claim",
            claim_number="1",
            quoted_text="A method comprising...",
            normalized_meaning="method steps",
            verified=True,
            verification_method="source-fetch",
            confidence=0.9,
        )
        validator = EvidenceValidator()
        issues = validator.validate(ev)
        assert len(issues) == 0
        assert validator.is_sufficient_for_conclusion(ev) is True

    def test_verified_no_url(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            verified=True,
            quoted_text="some text",
        )
        validator = EvidenceValidator()
        issues = validator.validate(ev)
        codes = {i.code for i in issues}
        assert "EVIDENCE_VERIFIED_NO_URL" in codes

    def test_no_location_for_conclusion(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            source_url="https://example.com",
            quoted_text="some text",
            verified=True,
            verification_method="source-fetch",
            confidence=0.9,
        )
        validator = EvidenceValidator()
        issues = validator.validate(ev, require_location=True)
        codes = {i.code for i in issues}
        assert "EVIDENCE_NO_LOCATION" in codes

    def test_low_confidence(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            source_url="https://example.com",
            location_type="claim",
            claim_number="1",
            quoted_text="text",
            verified=True,
            verification_method="source-fetch",
            confidence=0.2,
        )
        validator = EvidenceValidator()
        issues = validator.validate(ev)
        codes = {i.code for i in issues}
        assert "EVIDENCE_LOW_CONFIDENCE" in codes
        assert validator.is_sufficient_for_conclusion(ev) is False

    def test_user_input_no_url_ok(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="user-input",
            quoted_text="user description",
            verified=True,
            verification_method="user-provided",
            location_type="paragraph",
            confidence=0.8,
        )
        validator = EvidenceValidator()
        issues = validator.validate(ev)
        codes = {i.code for i in issues}
        assert "EVIDENCE_VERIFIED_NO_URL" not in codes


# ─── Date Validation ──────────────────────────────────────────────────

class TestDateValidator:
    def test_post_priority(self):
        doc = PriorArtDocument(
            id="DOC-001",
            type="patent",
            publication_date="2025-06-01",
        )
        validator = DateValidator()
        issues = validator.validate(doc, "2024-01-01")
        codes = {i.code for i in issues}
        assert "DATE_POST_PRIORITY" in codes

    def test_valid_date(self):
        doc = PriorArtDocument(
            id="DOC-001",
            type="patent",
            publication_date="2020-01-01",
        )
        validator = DateValidator()
        issues = validator.validate(doc, "2023-01-01")
        assert len(issues) == 0

    def test_missing_date(self):
        doc = PriorArtDocument(id="DOC-001", type="patent")
        validator = DateValidator()
        issues = validator.validate(doc, "2023-01-01")
        codes = {i.code for i in issues}
        assert "DATE_MISSING" in codes


# ─── Feature Coverage Validation ──────────────────────────────────────

class TestFeatureCoverageValidator:
    def test_all_covered(self):
        validator = FeatureCoverageValidator()
        issues = validator.validate(
            feature_ids=["F-001", "F-002"],
            evidence_feature_map={
                "EV-001": ["F-001", "F-002"],
            },
        )
        assert len(issues) == 0

    def test_uncovered_necessary(self):
        validator = FeatureCoverageValidator()
        issues = validator.validate(
            feature_ids=["F-001", "F-002", "F-003"],
            evidence_feature_map={
                "EV-001": ["F-001"],
                "EV-002": ["F-002"],
            },
        )
        codes = {i.code for i in issues}
        assert "FEATURE_UNCOVERED" in codes

    def test_partial_coverage(self):
        validator = FeatureCoverageValidator()
        issues = validator.validate(
            feature_ids=["F-001"],
            evidence_feature_map={},
        )
        codes = {i.code for i in issues}
        assert "FEATURE_UNCOVERED" in codes


# ─── Models ───────────────────────────────────────────────────────────

class TestFeature:
    def test_valid(self):
        f = Feature(id="F-001", text="cache eviction", kind="necessary")
        assert f.id == "F-001"

    def test_invalid_id(self):
        with pytest.raises(ValueError):
            Feature(id="feat-1", text="x", kind="necessary")

    def test_missing_text(self):
        with pytest.raises(ValueError):
            Feature(id="F-001", text="", kind="necessary")


class TestEvidenceItem:
    def test_valid(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            location_type="claim",
            claim_number="1",
            quoted_text="A method",
            verified=True,
            verification_method="source-fetch",
            confidence=0.9,
        )
        assert ev.has_location()
        assert ev.has_quoted_text()

    def test_no_location(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
        )
        assert not ev.has_location()

    def test_no_quoted_text(self):
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
        )
        assert not ev.has_quoted_text()


class TestPatentCaseState:
    def test_minimal(self):
        state = PatentCaseState(
            case=CaseMeta(id="case-test-001", status=CaseStatus.CREATED),
            request=CaseRequest(idea="A test idea"),
            mode="quick",
        )
        assert state.schema_version == "1.0"
        assert state.case.status == CaseStatus.CREATED
        assert state.features == []

    def test_json_serialization(self):
        state = PatentCaseState(
            case=CaseMeta(id="case-test-002", status=CaseStatus.CREATED),
            request=CaseRequest(idea="Novel cache algorithm"),
            mode="standard",
            features=[
                Feature(id="F-001", text="dynamic tier", kind="necessary"),
            ],
            budget=ExecutionBudget(max_search_calls=16),
        )
        json_str = state.model_dump_json(indent=2)
        data = json.loads(json_str)
        assert data["schema_version"] == "1.0"
        assert data["case"]["status"] == "CREATED"
        assert len(data["features"]) == 1


# ─── Quality Gate ──────────────────────────────────────────────────────

class TestQualityGate:
    def test_pass_with_valid_evidence(self):
        doc = PriorArtDocument(
            id="DOC-001",
            type="patent",
            publication_date="2020-01-01",
        )
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            source_url="https://example.com",
            location_type="claim",
            claim_number="1",
            quoted_text="A method comprising...",
            feature_ids=["F-001"],
            supports=["novelty:DOC-001:F-001"],
            verified=True,
            verification_method="source-fetch",
            confidence=0.9,
        )
        gate = QualityGate()
        errors, warnings, blocked = gate.run(
            evidence_list=[ev],
            documents={"DOC-001": doc},
            features_necessary=["F-001"],
            priority_date="2023-01-01",
            conclusion_ids=["novelty:DOC-001:F-001"],
        )
        assert len(errors) == 0
        assert blocked == []

    def test_block_conclusion_without_evidence(self):
        gate = QualityGate()
        errors, warnings, blocked = gate.run(
            evidence_list=[],
            documents={},
            features_necessary=["F-001"],
            priority_date="2023-01-01",
            conclusion_ids=["novelty:DOC-001:F-001"],
        )
        assert "novelty:DOC-001:F-001" in blocked

    def test_block_post_priority_document(self):
        doc = PriorArtDocument(
            id="DOC-001",
            type="patent",
            publication_date="2025-01-01",
        )
        ev = EvidenceItem(
            id="EV-001",
            document_id="DOC-001",
            source_type="patent",
            source_url="https://example.com",
            location_type="claim",
            claim_number="1",
            quoted_text="A method comprising...",
            feature_ids=["F-001"],
            supports=["novelty:DOC-001:F-001"],
            verified=True,
            verification_method="source-fetch",
            confidence=0.9,
        )
        gate = QualityGate()
        errors, warnings, blocked = gate.run(
            evidence_list=[ev],
            documents={"DOC-001": doc},
            features_necessary=["F-001"],
            priority_date="2023-01-01",
            conclusion_ids=["novelty:DOC-001:F-001"],
        )
        assert "novelty:DOC-001:F-001" in blocked
