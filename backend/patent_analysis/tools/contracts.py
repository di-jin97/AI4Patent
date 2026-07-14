"""Stable ToolCall contracts for patent fact retrieval.

These models deliberately contain source facts and provenance only.  Legal or
semantic conclusions are produced by Skills and deterministic domain services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: int | None = None


class ToolResponse(BaseModel):
    request_id: str
    status: Literal["success", "partial", "failed"] = "success"
    source: str
    retrieved_at: str = Field(default_factory=_now)
    source_url: str | None = None
    content_hash: str | None = None
    error: ToolError | None = None


class PatentSearchRequest(BaseModel):
    request_id: str
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None
    language: Literal["zh", "en"] = "en"
    before: str | None = None
    after: str | None = None
    assignee: str | None = None
    cpc: list[str] = Field(default_factory=list)


class PatentSearchResult(BaseModel):
    publication_number: str | None = None
    title: str = ""
    url: str
    snippet: str = ""
    publication_date: str | None = None
    assignee: str | None = None
    inventors: list[str] = Field(default_factory=list)
    cpc: list[str] = Field(default_factory=list)


class PatentSearchResponse(ToolResponse):
    results: list[PatentSearchResult] = Field(default_factory=list)
    next_cursor: str | None = None
    query_echo: str = ""


class BiblioRequest(BaseModel):
    request_id: str
    publication_number: str


class PatentBiblio(BaseModel):
    publication_number: str
    title: str = ""
    application_number: str | None = None
    priority_date: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None
    grant_date: str | None = None
    assignees: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    ipc: list[str] = Field(default_factory=list)
    cpc: list[str] = Field(default_factory=list)
    abstract: str = ""
    url: str
    field_provenance: dict[str, str] = Field(default_factory=dict)


class BiblioResponse(ToolResponse):
    biblio: PatentBiblio | None = None


class SectionRequest(BaseModel):
    request_id: str
    publication_number: str
    sections: list[Literal["abstract", "claims", "description"]] = Field(
        default_factory=lambda: ["abstract", "claims"]
    )
    claim_numbers: list[str] = Field(default_factory=list)
    max_characters: int = Field(default=30_000, ge=1_000, le=200_000)
    cursor: str | None = None


class TextSection(BaseModel):
    section: Literal["abstract", "claims", "description"]
    locator: str
    text: str
    content_hash: str
    claim_number: str | None = None


class SectionResponse(ToolResponse):
    publication_number: str
    sections: list[TextSection] = Field(default_factory=list)
    next_cursor: str | None = None
    raw_artifact_id: str | None = None


class PassageSearchRequest(BaseModel):
    request_id: str
    publication_number: str
    feature_texts: list[str] = Field(min_length=1)
    section_scope: list[Literal["abstract", "claims", "description"]] = Field(
        default_factory=lambda: ["claims", "description"]
    )
    max_passages_per_feature: int = Field(default=3, ge=1, le=10)


class PassageMatch(BaseModel):
    feature_text: str
    locator: str
    text: str
    score: float = Field(ge=0, le=1)
    content_hash: str


class PassageSearchResponse(ToolResponse):
    publication_number: str
    matches: list[PassageMatch] = Field(default_factory=list)


class RelationsRequest(BaseModel):
    request_id: str
    publication_number: str


class PatentRelations(BaseModel):
    family_members: list[str] = Field(default_factory=list)
    cited_by: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    completeness: Literal["complete", "partial", "unavailable"] = "unavailable"


class RelationsResponse(ToolResponse):
    publication_number: str
    relations: PatentRelations = Field(default_factory=PatentRelations)
