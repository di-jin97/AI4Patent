"""IDEA review tests across the current legacy API and the new P0 foundation.

These tests deliberately use FakeSearchProvider for prior-art data. They do not
make a paid model call or depend on live Exa availability.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from backend.patent_analysis.adapters.base import SearchRequest, SearchResult, FetchRequest
from backend.patent_analysis.adapters.exa import ExaAdapter
from backend.patent_analysis.adapters.fake import FakeSearchProvider
from backend.patent_analysis.adapters.opencode_mcp_bridge import OpenCodeMCPBridgeError
from backend.patent_analysis.domain.models import (
    CaseMeta,
    CaseRequest,
    CaseStatus,
    EvidenceItem,
    Feature,
    FullTextRecord,
    PatentCaseState,
    PriorArtDocument,
)
from backend.patent_analysis.persistence.state_store import StateStore
from backend.patent_analysis.services.documents import deduplicate_documents, rank_documents
from backend.patent_analysis.services.evidence import extract_evidence
from backend.patent_analysis.services.novelty import evaluate_novelty
from backend.patent_analysis.services.quality import run_quality_gate
from backend.patent_analysis.workflow.orchestrator import WorkflowOrchestrator, WorkflowStep


def _case() -> PatentCaseState:
    return PatentCaseState(
        case=CaseMeta(id="idea-e2e-001", status=CaseStatus.CREATED),
        request=CaseRequest(idea="依据工作负载动态选择缓存层级，降低读取延迟。"),
        mode="quick",
        priority_date="2023-01-01",
        features=[
            Feature(id="F-001", text="动态选择缓存层级", kind="necessary", limitation="step"),
            Feature(id="F-002", text="根据工作负载调整缓存", kind="necessary", limitation="step"),
        ],
    )


@pytest.mark.asyncio
async def test_idea_prior_art_pipeline_is_evidence_bound_and_persisted():
    """Exercise search/fetch/dedupe/rank/evidence/novelty/quality as one case."""
    state = _case()
    provider = FakeSearchProvider()
    url = "https://patents.google.com/patent/US1234567A1/en"
    provider.add_search_results("dynamic cache", [
        SearchResult(
            title="Dynamic cache tier selection",
            url=url,
            snippet="Selects cache tiers dynamically from workload characteristics.",
            published_date="2020-01-01",
            publication_number="US1234567A1",
        ),
        SearchResult(
            title="Duplicate result",
            url=url,
            snippet="Duplicate",
            published_date="2020-01-01",
            publication_number="US1234567A1",
        ),
    ])
    provider.add_fetch_content(url, "Claim 1: dynamically select a cache tier based on workload.")

    response = await provider.search(SearchRequest(
        request_id="idea-search-001", query="dynamic cache workload", limit=20,
    ))
    assert response.provider == "fake"
    assert len(provider.search_calls) == 1

    candidates = [
        PriorArtDocument(
            id=f"DOC-{index:03d}", type="patent", title=result.title,
            abstract=result.snippet, publication_number=result.publication_number,
            publication_date=result.published_date, source_url=result.url,
        )
        for index, result in enumerate(response.results, start=1)
    ]
    state.documents = deduplicate_documents(candidates)
    assert [doc.id for doc in state.documents] == ["DOC-001"]

    ranking = rank_documents(state.documents, [feature.text for feature in state.features])
    assert ranking[0].document_id == "DOC-001"

    fetch = await provider.fetch(FetchRequest(request_id="idea-fetch-001", urls=[url]))
    assert fetch.results[0].status == "success"
    state.full_text = [FullTextRecord(
        document_id="DOC-001", content_hash="fixture-content-v1", url=url,
        fetched_at="2026-07-13T00:00:00Z", content_preview=fetch.results[0].content,
        char_count=fetch.results[0].char_count,
    )]
    state.evidence = [extract_evidence(
        state=state, document_id="DOC-001", source_type="patent", source_url=url,
        location_type="claim", claim_number="1", paragraph_range=None,
        page_range=None, section=None, quoted_text=fetch.results[0].content,
        normalized_meaning="依据工作负载动态选择缓存层级", feature_ids=["F-001", "F-002"],
        supports=["novelty:DOC-001"], confidence=0.95, verified=True,
        verification_method="source-fetch",
    )]
    state.novelty = evaluate_novelty(
        state.features, state.documents, state.evidence, state.priority_date,
    )
    state.quality = run_quality_gate(state)

    assert state.novelty.overall == "not-novel"
    assert state.quality.passed is True
    assert state.evidence[0].document_version == "fixture-content-v1"

    with tempfile.TemporaryDirectory() as directory:
        store = StateStore(Path(directory) / "cases.db")
        store.create_case(state)
        loaded = store.load_case(state.case.id)
    assert loaded is not None
    assert loaded.novelty is not None
    assert loaded.novelty.overall == "not-novel"


class _AdvanceStep(WorkflowStep):
    def __init__(self, name: str, start: CaseStatus, target: CaseStatus) -> None:
        self.name = name
        self.allowed_from = frozenset({start})
        self.target = target

    async def run(self, state: PatentCaseState) -> PatentCaseState:
        return state


@pytest.mark.asyncio
async def test_idea_workflow_persists_one_revision_per_step():
    """A checkpoint must advance the State revision once, not twice."""
    state = _case()
    with tempfile.TemporaryDirectory() as directory:
        store = StateStore(Path(directory) / "cases.db")
        store.create_case(state)
        final_state = await WorkflowOrchestrator(store).run_case(state.case.id, [
            _AdvanceStep("intake", CaseStatus.CREATED, CaseStatus.INTAKE_PARSED),
            _AdvanceStep("features", CaseStatus.INTAKE_PARSED, CaseStatus.FEATURES_EXTRACTED),
        ])
        persisted = store.load_case(state.case.id)

    assert final_state.case.status == CaseStatus.FEATURES_EXTRACTED
    assert final_state.case.revision == 2
    assert persisted is not None
    assert persisted.case.revision == 2
    assert len(persisted.trace) == 2


class _UnavailableBridge:
    async def execute(self, tool_name: str, payload: dict) -> object:
        raise OpenCodeMCPBridgeError(f"{tool_name} unavailable")


@pytest.mark.asyncio
async def test_idea_search_provider_surfaces_bridge_failure():
    """An unavailable MCP must be a failed provider response, never empty success."""
    response = await ExaAdapter(bridge=_UnavailableBridge()).search(SearchRequest(
        request_id="idea-search-failure", query="cache", limit=5,
    ))
    assert response.status == "failed"
    assert "unavailable" in (response.error or "")


class _RecordingBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, tool_name: str, payload: dict) -> object:
        self.calls.append((tool_name, payload))
        return {"results": []}


@pytest.mark.asyncio
async def test_idea_exa_adapter_uses_remote_server_tool_names():
    """OpenCode prefixes tools, but the direct remote MCP server does not."""
    bridge = _RecordingBridge()
    provider = ExaAdapter(bridge=bridge)

    await provider.search(SearchRequest(request_id="direct-tool-search", query="cache", limit=5))
    await provider.fetch(FetchRequest(request_id="direct-tool-fetch", urls=["https://example.test"]))

    assert bridge.calls[0][0] == "web_search_exa"
    assert bridge.calls[1][0] == "web_fetch_exa"


@pytest.mark.asyncio
async def test_legacy_idea_api_streams_agent_result(monkeypatch):
    """The existing IDEA-review endpoint remains usable while Case API is not yet P1 work."""
    backend_dir = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(backend_dir))
    try:
        import main as application

        async def fake_run_task(text, model, files, session_id, task_id):
            assert "patent-IDEA-analyzer" in text
            yield {"type": "output", "text": "IDEA_REVIEW_FIXTURE_OK"}
            yield {"type": "done", "result": "IDEA_REVIEW_FIXTURE_OK", "session_id": "session-fixture"}

        monkeypatch.setattr(application, "run_task", fake_run_task)
        response = await application.run(application.Task(
            text="请加载 patent-IDEA-analyzer skill 并评审缓存方案",
            model="deepseek/deepseek-v4-pro", files=[], session_id=None,
        ))
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    finally:
        sys.path.pop(0)

    assert response.status_code == 200
    streamed = "".join(chunks)
    assert "IDEA_REVIEW_FIXTURE_OK" in streamed
    assert "session-fixture" in streamed
