"""End-to-end acceptance tests for the replacement IDEA-review workflow.

All source material is synthetic fixture data.  This verifies the formerly
missing path: full text -> locatable evidence -> novelty / D1+D2 route ->
eight-section report and optional office exports.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.patent_analysis.adapters.base import SearchResult
from backend.patent_analysis.adapters.fake import FakeSearchProvider
from backend.patent_analysis.api import CaseCreateRequest, create_router
from backend.patent_analysis.persistence.state_store import StateStore
from backend.patent_analysis.workflow.orchestrator import WorkflowOrchestrator


@pytest.mark.asyncio
async def test_v1_workflow_creates_evidence_bound_d1_d2_report_and_exports(tmp_path: Path):
    provider = FakeSearchProvider()
    doc1 = "https://patents.google.com/patent/US1000001A1/en"
    doc2 = "https://patents.google.com/patent/US1000002A1/en"
    provider.add_search_results("动态选择缓存层级", [
        SearchResult(title="D1 cache tiers", url=doc1, publication_number="US1000001A1", published_date="2020-01-01"),
        SearchResult(title="D2 workload control", url=doc2, publication_number="US1000002A1", published_date="2021-01-01"),
    ])
    provider.add_fetch_content(doc1, "[claim:1] 动态选择缓存层级。")
    provider.add_fetch_content(doc2, "[claim:1] 根据工作负载调整缓存，并 combine 动态缓存层级以降低延迟。")

    store = StateStore(tmp_path / "cases.db")
    router = create_router(store, WorkflowOrchestrator(store), provider, tmp_path / "cases")
    endpoints = {route.path: route.endpoint for route in router.routes}
    created = await endpoints["/api/cases"](CaseCreateRequest(
        idea="动态选择缓存层级；根据工作负载调整缓存",
        priority_date="2023-01-01", requested_outputs=["markdown", "json", "docx", "xlsx"],
    ))
    case_id = created["case"]["id"]
    assert (await endpoints["/api/cases/{case_id}/run"](case_id))["started"] is True

    for _ in range(100):
        state = await endpoints["/api/cases/{case_id}"](case_id)
        if state["case"]["status"] in {"COMPLETED", "FAILED"}:
            break
        await asyncio.sleep(0.01)

    assert state["case"]["status"] == "COMPLETED"
    assert state["novelty"]["overall"] == "novel"  # No single document covers both features.
    assert state["inventiveness"]["overall"] == "not-inventive"
    assert state["commercial_value"]["scorecard"]["innovation"]["score"] == 2
    assert len(state["evidence"]) == 2
    assert all(item["verified"] and item["quoted_text"] for item in state["evidence"])
    names = {item["name"] for item in state["artifacts"]}
    assert {"idea-review.md", "idea-review.json", "idea-review.docx", "idea-review.xlsx"} <= names
    report = (tmp_path / "cases" / case_id / "artifacts" / "idea-review.md").read_text(encoding="utf-8")
    assert "## 评审速览（标准化 0–5 分）" in report
    assert "## 8. 审查意见与质量门" in report
    assert "ROUTE-001" in report
