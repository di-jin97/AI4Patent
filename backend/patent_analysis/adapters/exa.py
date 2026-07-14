"""Exa search provider adapter via OpenCode MCP bridge.

按 design doc Section 7.4 定义。
当前未能直接调用 Exa MCP SDK，故通过 constrained agent bridge 桥接。
"""

from __future__ import annotations

import json
import uuid
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
from .opencode_mcp_bridge import OpenCodeMCPBridge


class ExaAdapter(SearchProvider):
    """Exa 适配器 — 通过 OpenCode MCP 桥接调用 Exa 工具"""

    def __init__(self, bridge: OpenCodeMCPBridge | None = None) -> None:
        self._bridge = bridge or OpenCodeMCPBridge()

    async def search(self, request: SearchRequest) -> SearchResponse:
        try:
            raw = await self._bridge.execute("exa_web_search_exa", {
                "query": request.query,
                "numResults": request.limit,
            })
            if raw is None:
                raise RuntimeError("OpenCode MCP bridge returned no search response")
            results = self._parse_search_results(raw)
            return SearchResponse(
                request_id=request.request_id,
                results=results,
                total_count=len(results),
                provider="exa",
                idempotency_key=request.idempotency_key,
            )
        except Exception as e:
            return SearchResponse(
                request_id=request.request_id,
                status="failed",
                error=str(e),
                idempotency_key=request.idempotency_key,
            )

    async def fetch(self, request: FetchRequest) -> FetchResponse:
        try:
            raw = await self._bridge.execute("exa_web_fetch_exa", {
                "urls": request.urls,
                "maxCharacters": request.max_characters,
            })
            if raw is None:
                raise RuntimeError("OpenCode MCP bridge returned no fetch response")
            results = self._parse_fetch_results(raw, request.urls)
            return FetchResponse(
                request_id=request.request_id,
                results=results,
                provider="exa",
                idempotency_key=request.idempotency_key,
            )
        except Exception as e:
            return FetchResponse(
                request_id=request.request_id,
                status="failed",
                error=str(e),
                idempotency_key=request.idempotency_key,
            )

    @staticmethod
    def _parse_search_results(raw: Any) -> list[SearchResult]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []

        items: list[dict] = []
        if isinstance(raw, dict):
            items = raw.get("results", []) or raw.get("data", [])
        elif isinstance(raw, list):
            items = raw

        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("text", "") or item.get("snippet", ""),
                    published_date=item.get("publishedDate") or item.get("published_date"),
                ))
        return results

    @staticmethod
    def _parse_fetch_results(raw: Any, urls: list[str]) -> list[FetchResult]:
        results = []
        for url in urls:
            content = ""
            if isinstance(raw, str):
                content = raw
            elif isinstance(raw, dict):
                content = (
                    raw.get("texts", {}).get(url, "")
                    or raw.get("results", {}).get(url, "")
                    or raw.get(url, "")
                    or str(raw)
                )
            elif isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and item.get("url") == url:
                        content = item.get("text", "") or str(item)
                        break
            else:
                content = str(raw) if raw else ""

            results.append(FetchResult(
                url=url,
                content=content,
                char_count=len(content),
                status="success" if content else "failed",
            ))
        return results
