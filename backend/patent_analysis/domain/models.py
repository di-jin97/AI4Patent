"""Core Pydantic models for Patent Innovation Analysis.

基于 design doc Section 6.1-6.4 定义。
所有模型使用 Pydantic v2，stable ID 前缀固定。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CaseStatus(str, Enum):
    CREATED = "CREATED"
    INTAKE_PARSED = "INTAKE_PARSED"
    FEATURES_EXTRACTED = "FEATURES_EXTRACTED"
    SEARCH_PLANNED = "SEARCH_PLANNED"
    SEARCHING = "SEARCHING"
    SEARCH_COMPLETED = "SEARCH_COMPLETED"
    DOCUMENTS_RANKED = "DOCUMENTS_RANKED"
    FULLTEXT_FETCHED = "FULLTEXT_FETCHED"
    EVIDENCE_EXTRACTED = "EVIDENCE_EXTRACTED"
    NOVELTY_EVALUATED = "NOVELTY_EVALUATED"
    INVENTIVENESS_EVALUATED = "INVENTIVENESS_EVALUATED"
    COMMERCIAL_VALUE_EVALUATED = "COMMERCIAL_VALUE_EVALUATED"
    QUALITY_VALIDATED = "QUALITY_VALIDATED"
    REPORT_RENDERED = "REPORT_RENDERED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


DOCUMENT_TYPES = frozenset({"patent", "paper", "standard", "whitepaper", "web", "product", "other"})
SOURCE_TYPES = frozenset({"patent", "paper", "standard", "whitepaper", "user-input", "web", "product"})
LOCATION_TYPES = frozenset({"claim", "paragraph", "page", "section", "abstract", "figure", "table"})
VERIFICATION_METHODS = frozenset({"source-fetch", "user-provided", "manual", "exa-bridge"})
MODES = frozenset({"quick", "standard", "deep", "commercial"})
JURISDICTIONS = frozenset({"CN", "US", "EP", "WO", "JP", "KR", "DE", "GB", "FR", "TW", "OTHER"})
LIMITATION_KINDS = frozenset({"functional", "structural", "parameter", "step", "composition"})

_FEATURE_ID_RE = re.compile(r"^F-\d{3,}$")
_EVIDENCE_ID_RE = re.compile(r"^EV-\d{3,}$")
_DOCUMENT_ID_RE = re.compile(r"^DOC-\d{3,}$")
_ROUTE_ID_RE = re.compile(r"^ROUTE-\d{3,}$")
_QUERY_ID_RE = re.compile(r"^Q-\d{3,}$")


# ─── supporting types ──────────────────────────────────────────────────

class EvidenceRef(BaseModel):
    evidence_id: str = Field(pattern=r"^EV-\d{3,}$")
    relationship: Literal["supports", "contradicts", "context"]


class CaseMeta(BaseModel):
    id: str
    status: CaseStatus
    revision: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CaseRequest(BaseModel):
    idea: str
    requested_outputs: list[str] = Field(default_factory=lambda: ["chat", "markdown", "json"])
    input_hash: str = ""

    @field_validator("input_hash")
    @classmethod
    def _set_input_hash(cls, v: str, info: Any) -> str:
        if v:
            return v
        idea = info.data.get("idea", "")
        return hashlib.sha256(idea.encode()).hexdigest()[:16]


# ─── Feature ───────────────────────────────────────────────────────────

class Feature(BaseModel):
    id: str = Field(pattern=r"^F-\d{3,}$")
    text: str = Field(min_length=1)
    kind: Literal["necessary", "optional"]
    limitation: Literal["functional", "structural", "parameter", "step", "composition"] = "functional"
    source: list[EvidenceRef] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_feature_id(cls, v: str) -> str:
        if not _FEATURE_ID_RE.match(v):
            raise ValueError(f"Invalid feature ID: {v}, expected F-NNN")
        return v


# ─── Evidence ──────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    id: str = Field(pattern=r"^EV-\d{3,}$")
    document_id: str = Field(pattern=r"^DOC-\d{3,}$")
    document_version: str = ""
    source_type: Literal["patent", "paper", "standard", "whitepaper", "user-input", "web", "product"]
    source_url: str | None = None
    location_type: Literal["claim", "paragraph", "page", "section", "abstract", "figure", "table"] | None = None
    claim_number: str | None = None
    paragraph_range: str | None = None
    page_range: str | None = None
    section: str | None = None
    quoted_text: str = ""
    normalized_meaning: str = ""
    feature_ids: list[str] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    verified: bool = False
    verification_method: Literal["source-fetch", "user-provided", "manual", "exa-bridge"] | None = None
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("id")
    @classmethod
    def _validate_evidence_id(cls, v: str) -> str:
        if not _EVIDENCE_ID_RE.match(v):
            raise ValueError(f"Invalid evidence ID: {v}, expected EV-NNN")
        return v

    def has_location(self) -> bool:
        return any([
            self.location_type is not None,
            self.claim_number is not None,
            self.paragraph_range is not None,
            self.page_range is not None,
            self.section is not None,
        ])

    def has_source_url(self) -> bool:
        return bool(self.source_url and self.source_url.strip())

    def has_quoted_text(self) -> bool:
        return bool(self.quoted_text and self.quoted_text.strip())


# ─── Documents ─────────────────────────────────────────────────────────

class PriorArtDocument(BaseModel):
    id: str = Field(pattern=r"^DOC-\d{3,}$")
    type: Literal["patent", "paper", "standard", "whitepaper", "web", "product", "other"]
    title: str = ""
    publication_number: str | None = None
    application_number: str | None = None
    publication_date: str | None = None
    filing_date: str | None = None
    assignee: str | None = None
    inventor: str | None = None
    ipc_classifications: list[str] = Field(default_factory=list)
    cpc_classifications: list[str] = Field(default_factory=list)
    abstract: str = ""
    claims_text: str = ""
    description_snippet: str = ""
    source_url: str | None = None
    source_provider: str = "exa"
    source_raw: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    normalized_url: str | None = None
    metadata_status: dict[str, Literal["verified", "missing", "conflicting"]] = Field(default_factory=dict)
    priority_date: str | None = None

    @field_validator("id")
    @classmethod
    def _validate_doc_id(cls, v: str) -> str:
        if not _DOCUMENT_ID_RE.match(v):
            raise ValueError(f"Invalid document ID: {v}, expected DOC-NNN")
        return v


class PatentFamily(BaseModel):
    family_id: str
    members: list[str] = Field(default_factory=list)
    canonical_id: str = ""


# ─── Search ────────────────────────────────────────────────────────────

class Query(BaseModel):
    id: str = Field(pattern=r"^Q-\d{3,}$")
    query_text: str
    language: Literal["zh", "en"] = "en"
    phase: Literal["A", "B", "C", "D"] = "A"
    types: list[str] = Field(default_factory=lambda: ["patent", "paper"])
    intent: str = ""
    limit: int = 20
    executed: bool = False

    @field_validator("id")
    @classmethod
    def _validate_query_id(cls, v: str) -> str:
        if not _QUERY_ID_RE.match(v):
            raise ValueError(f"Invalid query ID: {v}, expected Q-NNN")
        return v


class SearchPlan(BaseModel):
    queries: list[Query] = Field(default_factory=list)
    phases: dict[str, list[str]] = Field(default_factory=dict)
    strategy: str = ""


class SearchRun(BaseModel):
    query_id: str
    idempotency_key: str
    provider: str = "exa"
    request_raw: dict[str, Any] = Field(default_factory=dict)
    response_raw: dict[str, Any] = Field(default_factory=dict)
    result_count: int = 0
    status: Literal["success", "partial", "failed", "timeout", "rate_limited"] = "success"
    duration_ms: int = 0
    error: str | None = None
    attempt: int = 1


# ─── Ranking & Full Text ───────────────────────────────────────────────

class RankingResult(BaseModel):
    document_id: str
    base_score: float = 0.0
    feature_coverage: float = 0.0
    field_similarity: float = 0.0
    problem_similarity: float = 0.0
    claim_similarity: float = 0.0
    classification_similarity: float = 0.0
    citation_signal: float = 0.0
    source_reliability: float = 0.0
    date_validity: float = 1.0
    duplicate_risk: float = 0.0
    novelty_score: float = 0.0
    d1_score: float = 0.0
    d2_score: float = 0.0
    fetch_priority: float = 0.0


class FullTextRecord(BaseModel):
    document_id: str
    content_hash: str
    url: str
    fetched_at: str
    status: Literal["fetched", "failed", "skipped", "invalid_url"] = "fetched"
    content_preview: str = ""
    char_count: int = 0
    fetch_duration_ms: int = 0
    error: str | None = None


# ─── Evaluation ────────────────────────────────────────────────────────

class NoveltyEvaluationResult(BaseModel):
    by_document: list[dict[str, Any]] = Field(default_factory=list)
    overall: Literal["novel", "not-novel", "uncertain"] = "uncertain"
    evidence_ids: list[str] = Field(default_factory=list)
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InventiveStepRoute(BaseModel):
    id: str = Field(pattern=r"^ROUTE-\d{3,}$")
    d1_document_id: str
    difference_feature_ids: list[str] = Field(default_factory=list)
    actual_technical_problem: str = ""
    d2_document_ids: list[str] = Field(default_factory=list)
    motivation_evidence_ids: list[str] = Field(default_factory=list)
    obstacle_evidence_ids: list[str] = Field(default_factory=list)
    synergy_evidence_ids: list[str] = Field(default_factory=list)
    conclusion: Literal["inventive", "not-inventive", "uncertain"] = "uncertain"

    @field_validator("id")
    @classmethod
    def _validate_route_id(cls, v: str) -> str:
        if not _ROUTE_ID_RE.match(v):
            raise ValueError(f"Invalid route ID: {v}, expected ROUTE-NNN")
        return v


class InventiveStepResult(BaseModel):
    routes: list[InventiveStepRoute] = Field(default_factory=list)
    strongest_route_id: str | None = None
    overall: Literal["inventive", "not-inventive", "uncertain"] = "uncertain"
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CommercialValueResult(BaseModel):
    enforceability: dict[str, Any] = Field(default_factory=dict)
    avoidability: dict[str, Any] = Field(default_factory=dict)
    market_potential: dict[str, Any] = Field(default_factory=dict)
    standard_essential: dict[str, Any] = Field(default_factory=dict)
    maturity: dict[str, Any] = Field(default_factory=dict)
    implementer_analysis: dict[str, Any] = Field(default_factory=dict)
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Quality ───────────────────────────────────────────────────────────

class QualityGateResult(BaseModel):
    passed: bool = True
    errors: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)
    blocked_conclusion_ids: list[str] = Field(default_factory=list)
    validated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Budget ────────────────────────────────────────────────────────────

class ExecutionBudget(BaseModel):
    max_search_calls: int = 16
    max_fetch_calls: int = 16
    max_documents: int = 60
    max_full_text_documents: int = 12
    max_tokens: int = 160_000
    max_workflow_duration_seconds: int = 1_800
    max_retries_per_tool: int = 2
    max_d1_routes: int = 3
    max_d2_per_feature: int = 2
    consumed: dict[str, int] = Field(default_factory=dict)


# ─── Auxiliary ─────────────────────────────────────────────────────────

class CaseError(BaseModel):
    code: str
    message: str
    path: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    recoverable: bool = False


class TraceEvent(BaseModel):
    event: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    step: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    name: str
    format: Literal["chat", "markdown", "json", "docx", "xlsx"]
    path: str = ""
    content_hash: str = ""
    state_revision: int = 0
    state_hash: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Root State ────────────────────────────────────────────────────────

class PatentCaseState(BaseModel):
    """案件唯一事实来源 — design doc Section 6.1."""
    schema_version: Literal["1.0"] = "1.0"
    case: CaseMeta
    request: CaseRequest
    mode: Literal["quick", "standard", "deep", "commercial"]
    jurisdiction: list[str] = Field(default_factory=lambda: ["CN"])
    priority_date: str | None = None
    invention: dict[str, Any] = Field(default_factory=dict)
    features: list[Feature] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    search_plan: SearchPlan | None = None
    queries: list[Query] = Field(default_factory=list)
    search_runs: list[SearchRun] = Field(default_factory=list)
    documents: list[PriorArtDocument] = Field(default_factory=list)
    patent_families: list[PatentFamily] = Field(default_factory=list)
    ranking: list[RankingResult] = Field(default_factory=list)
    full_text: list[FullTextRecord] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    novelty: NoveltyEvaluationResult | None = None
    inventiveness: InventiveStepResult | None = None
    commercial_value: CommercialValueResult | None = None
    quality: QualityGateResult | None = None
    budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    errors: list[CaseError] = Field(default_factory=list)
    trace: list[TraceEvent] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
