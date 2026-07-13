"""Fake search provider for testing.

按 design doc Section 12.2 要求，所有 provider 测试必须使用 fake，
不依赖在线 Exa。
"""

from __future__ import annotations

import hashlib
from typing import Any

from .base import (
    SearchProvider,
    SearchRequest,
    SearchResponse,
    SearchResult,
    FetchRequest,
    FetchResponse,
    FetchResult,
)


class FakeSearchProvider(SearchProvider):
    """测试用 fake provider，返回预定义数据"""

    def __init__(self) -> None:
        self._search_store: dict[str, list[SearchResult]] = {}
        self._fetch_store: dict[str, str] = {}
        self.search_calls: list[SearchRequest] = []
        self.fetch_calls: list[FetchRequest] = []

    def add_search_results(
        self, query_pattern: str, results: list[SearchResult]
    ) -> None:
        self._search_store[query_pattern] = results

    def add_fetch_content(self, url: str, content: str) -> None:
        self._fetch_store[url] = content

    async def search(self, request: SearchRequest) -> SearchResponse:
        self.search_calls.append(request)

        results: list[SearchResult] = []
        for pattern, stored in self._search_store.items():
            if pattern.lower() in request.query.lower():
                results.extend(stored)

        return SearchResponse(
            request_id=request.request_id,
            results=results[:request.limit],
            total_count=len(results),
            provider="fake",
            idempotency_key=request.idempotency_key,
        )

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        self.fetch_calls.append(request)

        fetch_results = []
        for url in request.urls:
            content = self._fetch_store.get(url, f"Mock content for {url}")
            fetch_results.append(FetchResult(
                url=url,
                content=content,
                title=f"Title for {url}",
                char_count=len(content),
                status="success" if url in self._fetch_store else "success",
            ))

        return FetchResponse(
            request_id=request.request_id,
            results=fetch_results,
            provider="fake",
            idempotency_key=request.idempotency_key,
        )
