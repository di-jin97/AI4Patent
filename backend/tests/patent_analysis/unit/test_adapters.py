"""Unit tests for provider adapters and document services.

按 design doc Section 12.1 契约测试。
"""

import pytest

from backend.patent_analysis.adapters.base import SearchRequest, SearchResponse, FetchRequest, FetchResponse, SearchResult
from backend.patent_analysis.adapters.fake import FakeSearchProvider
from backend.patent_analysis.domain.models import PriorArtDocument
from backend.patent_analysis.services.documents import (
    normalize_url,
    normalize_patent_number,
    deduplicate_documents,
    build_patent_google_url,
    generate_document_hash,
    rank_documents,
)
from backend.patent_analysis.services import documents


# ─── Fake Provider ────────────────────────────────────────────────────

class TestFakeProvider:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        provider = FakeSearchProvider()
        provider.add_search_results("cache", [
            SearchResult(
                title="Dynamic Cache Patent",
                url="https://example.com/patent1",
                snippet="A cache system...",
                published_date="2020-01-01",
            ),
        ])
        req = SearchRequest(
            request_id="req-1",
            query="dynamic cache optimization",
            limit=10,
        )
        resp = await provider.search(req)
        assert resp.status == "success"
        assert len(resp.results) == 1
        assert resp.results[0].title == "Dynamic Cache Patent"

    @pytest.mark.asyncio
    async def test_search_no_match(self):
        provider = FakeSearchProvider()
        req = SearchRequest(request_id="req-2", query="something", limit=10)
        resp = await provider.search(req)
        assert resp.status == "success"
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_fetch_returns_content(self):
        provider = FakeSearchProvider()
        provider.add_fetch_content(
            "https://patents.google.com/patent/US123/en",
            "Patent full text here."
        )
        req = FetchRequest(
            request_id="req-3",
            urls=["https://patents.google.com/patent/US123/en"],
            max_characters=100000,
        )
        resp = await provider.fetch(req)
        assert resp.status == "success"
        assert len(resp.results) == 1
        assert resp.results[0].content == "Patent full text here."

    @pytest.mark.asyncio
    async def test_tracks_calls(self):
        provider = FakeSearchProvider()
        req = SearchRequest(request_id="req-4", query="test", limit=5)
        await provider.search(req)
        assert len(provider.search_calls) == 1
        assert provider.search_calls[0].query == "test"


# ─── URL Normalization ────────────────────────────────────────────────

class TestNormalizeURL:
    def test_remove_tracking_params(self):
        url = "https://example.com/doc?utm_source=abc&id=123"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "id=123" in result

    def test_remove_trailing_slash(self):
        assert normalize_url("https://example.com/doc/") == "https://example.com/doc"

    def test_remove_fragment(self):
        assert normalize_url("https://example.com/doc#section1") == "https://example.com/doc"

    def test_empty(self):
        assert normalize_url("") == ""


# ─── Patent Number Normalization ──────────────────────────────────────

class TestNormalizePatentNumber:
    def test_uppercase(self):
        assert normalize_patent_number("cn102063547b") == "CN102063547B"

    def test_remove_spaces(self):
        assert normalize_patent_number("US 10 964 349 B2") == "US10964349B2"

    def test_none(self):
        assert normalize_patent_number(None) is None

    def test_comma_removal(self):
        assert normalize_patent_number("US10,964,349B2") == "US10964349B2"


# ─── Deduplication ────────────────────────────────────────────────────

class TestDeduplicateDocuments:
    def test_dedupe_by_patent_number(self):
        docs = [
            PriorArtDocument(
                id="DOC-001", type="patent",
                publication_number="CN102063547B",
                title="Patent A",
            ),
            PriorArtDocument(
                id="DOC-002", type="patent",
                publication_number="CN102063547B",
                title="Patent A Duplicate",
            ),
        ]
        result = deduplicate_documents(docs)
        assert len(result) == 1
        assert result[0].id == "DOC-001"

    def test_dedupe_by_url(self):
        docs = [
            PriorArtDocument(
                id="DOC-003", type="patent",
                source_url="https://example.com/patent1",
                title="Doc A",
            ),
            PriorArtDocument(
                id="DOC-004", type="patent",
                source_url="https://example.com/patent1",
                title="Doc A copy",
            ),
        ]
        result = deduplicate_documents(docs)
        assert len(result) == 1

    def test_keep_unique(self):
        docs = [
            PriorArtDocument(id="DOC-005", type="patent", publication_number="US1"),
            PriorArtDocument(id="DOC-006", type="patent", publication_number="US2"),
        ]
        result = deduplicate_documents(docs)
        assert len(result) == 2


# ─── Google Patents URL ───────────────────────────────────────────────

class TestBuildPatentGoogleURL:
    def test_cn_patent(self):
        assert build_patent_google_url("CN102063547B") == "https://patents.google.com/patent/CN102063547B/en"

    def test_us_patent(self):
        assert build_patent_google_url("US10964349B2") == "https://patents.google.com/patent/US10964349B2/en"

    def test_empty(self):
        assert build_patent_google_url("") == ""


# ─── Document Hash ────────────────────────────────────────────────────

class TestGenerateDocumentHash:
    def test_same_content_same_hash(self):
        a = PriorArtDocument(id="DOC-001", type="patent", title="Same", abstract="Content")
        b = PriorArtDocument(id="DOC-002", type="patent", title="Same", abstract="Content")
        assert generate_document_hash(a) == generate_document_hash(b)

    def test_different_content_different_hash(self):
        a = PriorArtDocument(id="DOC-001", type="patent", title="A")
        b = PriorArtDocument(id="DOC-002", type="patent", title="B")
        assert generate_document_hash(a) != generate_document_hash(b)


# ─── Ranking ──────────────────────────────────────────────────────────

class TestRankDocuments:
    def test_returns_results_for_all_docs(self):
        docs = [
            PriorArtDocument(id="DOC-001", type="patent",
                             title="Dynamic cache optimization",
                             abstract="A method for cache management"),
            PriorArtDocument(id="DOC-002", type="patent",
                             title="Memory management",
                             abstract="Generic memory management"),
        ]
        results = rank_documents(docs, ["cache optimization", "memory"])
        assert len(results) == 2
        assert results[0].document_id == "DOC-001"

    def test_sorted_by_priority(self):
        docs = [
            PriorArtDocument(id="DOC-001", type="patent",
                             title="Cache system",
                             abstract="cache optimization"),
            PriorArtDocument(id="DOC-002", type="patent",
                             title="Unrelated topic",
                             abstract="something else"),
        ]
        results = rank_documents(docs, ["cache"])
        assert results[0].fetch_priority >= results[-1].fetch_priority

    def test_empty_features(self):
        docs = [PriorArtDocument(id="DOC-001", type="patent")]
        results = rank_documents(docs, [])
        assert len(results) == 1
        assert results[0].feature_coverage == 0.0
