"""Adapter that lets the generic workflow use the independent ToolCall layer."""

from __future__ import annotations

import re
from time import perf_counter

from .base import FetchRequest, FetchResponse, FetchResult, SearchProvider, SearchRequest, SearchResponse, SearchResult
from ..tools.contracts import PatentSearchRequest, SectionRequest
from ..tools.google_patents import GooglePatentsProvider


class GooglePatentsAdapter(SearchProvider):
    """SearchProvider compatibility adapter; source facts stay in ToolCalls."""

    def __init__(self, tools: GooglePatentsProvider | None = None) -> None:
        self.tools = tools or GooglePatentsProvider()

    async def search(self, request: SearchRequest) -> SearchResponse:
        started = perf_counter()
        response = await self.tools.search(PatentSearchRequest(
            request_id=request.request_id, query=request.query, limit=request.limit,
            language="zh" if request.language == "zh" else "en",
        ))
        return SearchResponse(
            request_id=request.request_id,
            results=[SearchResult(title=item.title, url=item.url, snippet=item.snippet, published_date=item.publication_date, publication_number=item.publication_number) for item in response.results],
            total_count=len(response.results), provider=response.source,
            duration_ms=int((perf_counter() - started) * 1000), status=response.status,
            error=response.error.message if response.error else None,
            idempotency_key=request.idempotency_key,
        )

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        started = perf_counter()
        results: list[FetchResult] = []
        for url in request.urls:
            number = _publication_number(url)
            if not number:
                results.append(FetchResult(url=url, status="invalid_url", error="Google Patents publication number missing"))
                continue
            response = await self.tools.get_sections(SectionRequest(
                request_id=f"{request.request_id}:{number}", publication_number=number,
                sections=["abstract", "claims", "description"], max_characters=request.max_characters,
            ))
            content = "\n".join(f"[{item.locator}] {item.text}" for item in response.sections)
            results.append(FetchResult(url=url, content=content, char_count=len(content), status="success" if response.status == "success" and content else "failed", error=response.error.message if response.error else None))
        return FetchResponse(request_id=request.request_id, results=results, provider="google_patents", duration_ms=int((perf_counter() - started) * 1000), status="success" if all(item.status == "success" for item in results) else "partial", idempotency_key=request.idempotency_key)


def _publication_number(url: str) -> str | None:
    match = re.search(r"/patent/([^/?#]+)", url)
    return match.group(1) if match else None
