from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.patent_analysis.adapters.base import SearchResult
from backend.patent_analysis.adapters.fake import FakeSearchProvider
from backend.patent_analysis.api import CaseCreateRequest, create_router
from backend.patent_analysis.persistence.state_store import StateStore
from backend.patent_analysis.workflow.orchestrator import WorkflowOrchestrator


def _endpoints(tmp_path: Path):
    store = StateStore(tmp_path / "cases.db")
    provider = FakeSearchProvider()
    provider.add_search_results("动态缓存", [
        SearchResult(title="Cache patent", url="https://example.test/patent/US1", snippet="cache"),
    ])
    router = create_router(store, WorkflowOrchestrator(store), provider, tmp_path / "cases")
    return {route.path: route.endpoint for route in router.routes}


@pytest.mark.asyncio
async def test_case_api_runs_persisted_v1_workflow_and_writes_artifact(tmp_path: Path):
    endpoints = _endpoints(tmp_path)
    created = await endpoints["/api/cases"](CaseCreateRequest(idea="动态缓存；根据工作负载选择层级"))
    case_id = created["case"]["id"]

    started = await endpoints["/api/cases/{case_id}/run"](case_id)
    assert started["started"] is True

    for _ in range(100):
        state = await endpoints["/api/cases/{case_id}"](case_id)
        if state["case"]["status"] in {"COMPLETED", "FAILED"}:
            break
        await asyncio.sleep(0.01)

    assert state["case"]["status"] == "COMPLETED"
    assert state["novelty"]["overall"] == "uncertain"
    assert state["artifacts"][0]["name"] == "idea-review.md"
    artifact_response = await endpoints["/api/cases/{case_id}/artifacts/{artifact_name}"](
        case_id, "idea-review.md"
    )
    assert Path(artifact_response.path).is_file()

    events_response = await endpoints["/api/cases/{case_id}/events"](case_id)
    events = [chunk async for chunk in events_response.body_iterator]
    assert any("case_terminal" in chunk for chunk in events)


@pytest.mark.asyncio
async def test_case_api_rejects_missing_and_terminal_cases(tmp_path: Path):
    endpoints = _endpoints(tmp_path)
    with pytest.raises(HTTPException) as missing:
        await endpoints["/api/cases/{case_id}"]("no-such-case")
    assert missing.value.status_code == 404

    created = await endpoints["/api/cases"](CaseCreateRequest(idea="缓存方案"))
    case_id = created["case"]["id"]
    assert (await endpoints["/api/cases/{case_id}/cancel"](case_id))["ok"] is True
    with pytest.raises(HTTPException) as terminal:
        await endpoints["/api/cases/{case_id}/run"](case_id)
    assert terminal.value.status_code == 409
