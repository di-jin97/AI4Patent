"""Search provider abstract interface.

按 design doc Section 7.1 定义 SearchProvider 契约。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchRequest:
    request_id: str
    query: str
    language: str = "en"  # "zh" | "en"
    phase: str = "A"  # "A" | "B" | "C" | "D"
    types: list[str] = field(default_factory=lambda: ["patent", "paper"])
    limit: int = 20
    idempotency_key: str = ""
    timeout_ms: int = 30_000


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    published_date: str | None = None
    source_type: str = "patent"  # patent|paper|standard|whitepaper|web
    authors: list[str] = field(default_factory=list)
    publication_number: str | None = None


@dataclass
class SearchResponse:
    request_id: str
    results: list[SearchResult] = field(default_factory=list)
    total_count: int = 0
    provider: str = "exa"
    duration_ms: int = 0
    status: str = "success"  # success|partial|failed|timeout|rate_limited
    error: str | None = None
    idempotency_key: str = ""


@dataclass
class FetchRequest:
    request_id: str
    urls: list[str]
    max_characters: int = 100_000
    idempotency_key: str = ""
    timeout_ms: int = 30_000


@dataclass
class FetchResult:
    url: str
    content: str = ""
    title: str = ""
    char_count: int = 0
    status: str = "success"  # success|failed|invalid_url|timeout
    error: str | None = None


@dataclass
class FetchResponse:
    request_id: str
    results: list[FetchResult] = field(default_factory=list)
    provider: str = "exa"
    duration_ms: int = 0
    status: str = "success"
    error: str | None = None
    idempotency_key: str = ""


class SearchProvider(ABC):
    """检索提供者抽象接口"""

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        ...

    @abstractmethod
    async def fetch(self, request: FetchRequest) -> FetchResponse:
        ...
