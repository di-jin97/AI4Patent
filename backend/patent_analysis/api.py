"""Case API and SSE runtime for the structured IDEA-review beta."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .adapters.base import SearchProvider
from .domain.models import CaseMeta, CaseRequest, CaseStatus, PatentCaseState
from .persistence.state_store import StateStore
from .steps import build_default_steps
from .workflow.orchestrator import WorkflowOrchestrator, WorkflowStep


class CaseCreateRequest(BaseModel):
    idea: str = Field(min_length=1, max_length=50_000)
    mode: Literal["quick", "standard", "deep", "commercial"] = "standard"
    priority_date: str | None = None
    jurisdiction: list[str] = Field(default_factory=lambda: ["CN"])
    requested_outputs: list[Literal["chat", "markdown", "json", "docx", "xlsx"]] = Field(default_factory=lambda: ["chat", "markdown", "json"])


class CaseRuntime:
    """In-process task registry with replayable SSE events for active cases."""

    def __init__(self, store: StateStore, orchestrator: WorkflowOrchestrator) -> None:
        self.store = store
        self.orchestrator = orchestrator
        self.tasks: dict[str, asyncio.Task] = {}
        self.history: dict[str, list[dict]] = defaultdict(list)
        self.subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def emit(self, event: dict) -> None:
        case_id = event["case_id"]
        self.history[case_id].append(event)
        self.history[case_id] = self.history[case_id][-100:]
        for queue in list(self.subscribers[case_id]):
            queue.put_nowait(event)

    def start(self, case_id: str, steps: list[WorkflowStep]) -> bool:
        task = self.tasks.get(case_id)
        if task and not task.done():
            return False

        async def runner() -> None:
            try:
                state = await self.orchestrator.run_case(case_id, steps, event_callback=self.emit)
                self.emit({
                    "type": "case_terminal",
                    "case_id": case_id,
                    "status": state.case.status.value,
                    "revision": state.case.revision,
                })
            finally:
                self.tasks.pop(case_id, None)

        self.tasks[case_id] = asyncio.create_task(runner())
        return True

    def cancel(self, case_id: str) -> bool:
        task = self.tasks.get(case_id)
        if task and not task.done():
            self.orchestrator.cancel(case_id)
            self.emit({"type": "cancel_requested", "case_id": case_id})
            return True
        return self.store.cancel_case(case_id)

    async def event_stream(self, case_id: str) -> AsyncIterator[str]:
        for event in self.history[case_id]:
            yield _sse(event)
        state = self.store.load_case(case_id)
        if state and state.case.status in {CaseStatus.COMPLETED, CaseStatus.FAILED, CaseStatus.CANCELLED}:
            yield _sse({"type": "case_terminal", "case_id": case_id, "status": state.case.status.value})
            return
        queue: asyncio.Queue = asyncio.Queue()
        self.subscribers[case_id].add(queue)
        try:
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") == "case_terminal":
                    return
        finally:
            self.subscribers[case_id].discard(queue)


def create_router(
    store: StateStore,
    orchestrator: WorkflowOrchestrator,
    provider: SearchProvider,
    cases_root: Path,
    *,
    steps_factory: Callable[[SearchProvider, Path], list[WorkflowStep]] = build_default_steps,
) -> APIRouter:
    router = APIRouter(prefix="/api/cases", tags=["structured-idea-beta"])
    runtime = CaseRuntime(store, orchestrator)

    def require_case(case_id: str) -> PatentCaseState:
        state = store.load_case(case_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Case not found")
        return state

    @router.post("")
    async def create_case(request: CaseCreateRequest):
        case_id = f"case-{uuid.uuid4().hex}"
        state = PatentCaseState(
            case=CaseMeta(id=case_id, status=CaseStatus.CREATED),
            request=CaseRequest(idea=request.idea, requested_outputs=request.requested_outputs),
            mode=request.mode,
            priority_date=request.priority_date,
            jurisdiction=request.jurisdiction,
        )
        store.create_case(state)
        return _state_payload(state)

    @router.post("/{case_id}/run")
    async def run_case(case_id: str):
        state = require_case(case_id)
        if state.case.status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED, CaseStatus.FAILED}:
            raise HTTPException(status_code=409, detail=f"Case is terminal: {state.case.status.value}")
        started = runtime.start(case_id, steps_factory(provider, cases_root))
        return {"ok": True, "started": started, "case_id": case_id, "status": state.case.status.value}

    @router.get("/{case_id}")
    async def get_case(case_id: str):
        return _state_payload(require_case(case_id))

    @router.get("/{case_id}/events")
    async def case_events(case_id: str):
        require_case(case_id)
        return StreamingResponse(runtime.event_stream(case_id), media_type="text/event-stream")

    @router.post("/{case_id}/resume")
    async def resume_case(case_id: str):
        state = require_case(case_id)
        if state.case.status != CaseStatus.PARTIAL:
            raise HTTPException(status_code=409, detail="Only PARTIAL cases can be resumed")
        started = runtime.start(case_id, steps_factory(provider, cases_root))
        return {"ok": True, "started": started, "case_id": case_id}

    @router.post("/{case_id}/cancel")
    async def cancel_case(case_id: str):
        require_case(case_id)
        return {"ok": runtime.cancel(case_id), "case_id": case_id}

    @router.get("/{case_id}/artifacts/{artifact_name}")
    async def get_artifact(case_id: str, artifact_name: str):
        state = require_case(case_id)
        artifact = next((item for item in state.artifacts if item.name == artifact_name), None)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        path = Path(artifact.path).resolve()
        expected_root = (cases_root / case_id / "artifacts").resolve()
        if expected_root not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="Artifact unavailable")
        return FileResponse(path, filename=artifact.name)

    return router


def _state_payload(state: PatentCaseState) -> dict:
    return state.model_dump(mode="json")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
