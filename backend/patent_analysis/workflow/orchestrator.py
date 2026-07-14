"""Workflow step protocol and orchestrator.

按 design doc Section 7.4 定义的工作流步骤接口与编排器。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

from ..domain.models import (
    CaseMeta,
    CaseRequest,
    CaseStatus,
    ExecutionBudget,
    PatentCaseState,
    TraceEvent,
    CaseError,
)
from .budget import BudgetManager, BudgetExhaustedError, get_mode_budget
from .transitions import assert_transition, is_terminal


class WorkflowStep(ABC):
    name: str = ""
    allowed_from: frozenset[CaseStatus] = frozenset()
    target: CaseStatus

    def idempotency_key(self, input_data: Any, state: PatentCaseState) -> str:
        raw = f"{self.name}:{state.case.id}:{state.case.revision}:{hashlib.sha256(str(input_data).encode()).hexdigest()[:16]}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @abstractmethod
    async def run(self, state: PatentCaseState) -> PatentCaseState:
        ...


class WorkflowOrchestrator:
    """状态驱动的案件分析编排器"""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._cancel_tokens: dict[str, bool] = {}
        self._start_time: dict[str, float] = {}

    def cancel(self, case_id: str) -> None:
        self._cancel_tokens[case_id] = True

    def _is_cancelled(self, case_id: str) -> bool:
        return self._cancel_tokens.get(case_id, False)

    async def run_case(
        self,
        case_id: str,
        steps: list[WorkflowStep],
        *,
        budget_override: ExecutionBudget | None = None,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> PatentCaseState:
        state = self._store.load_case(case_id)
        if state is None:
            raise ValueError(f"Case not found: {case_id}")

        self._cancel_tokens[case_id] = False
        self._start_time[case_id] = time.time()
        budget = budget_override or state.budget

        try:
            for step in steps:
                if self._is_cancelled(case_id):
                    state = await self._transition(
                        state, step, CaseStatus.CANCELLED, "User cancelled"
                    )
                    break

                if is_terminal(state.case.status):
                    break

                if state.case.status not in step.allowed_from:
                    continue

                self._emit(event_callback, {
                    "type": "step_start",
                    "step": step.name,
                    "case_id": case_id,
                    "status": state.case.status.value,
                })

                try:
                    state = await step.run(state)
                    if state.case.status != step.target:
                        state = await self._checkpoint(state, step)
                except BudgetExhaustedError as e:
                    state = await self._transition(
                        state, step, CaseStatus.PARTIAL,
                        f"Budget exhausted: {e.kind}"
                    )
                    break
                except Exception as e:
                    state = await self._transition(
                        state, step, CaseStatus.FAILED, str(e)
                    )
                    break

                self._emit(event_callback, {
                    "type": "step_complete",
                    "step": step.name,
                    "case_id": case_id,
                    "status": state.case.status.value,
                })

        finally:
            self._cancel_tokens.pop(case_id, None)
            self._start_time.pop(case_id, None)

        return state

    async def _checkpoint(self, state: PatentCaseState, step: WorkflowStep) -> PatentCaseState:
        from_status = state.case.status
        target = step.target

        key = step.idempotency_key("", state)
        cached = self._store.check_idempotency(key)
        if cached is not None:
            state.case.status = target
            return state

        assert_transition(from_status, target)
        state.trace.append(TraceEvent(
            event=f"step_completed:{step.name}",
            step=step.name,
            detail={"from": from_status.value, "to": target.value},
        ))

        # StateStore is the only component that mutates revision/status while
        # persisting a checkpoint. Mutating them here as well used to make each
        # workflow step advance the revision twice.
        self._store.save_checkpoint(
            state.case.id, from_status, target, state
        )
        self._store.record_idempotency(state.case.id, key, "completed")
        return state

    async def _transition(
        self, state: PatentCaseState, step: WorkflowStep,
        to_status: CaseStatus, error_msg: str
    ) -> PatentCaseState:
        from_status = state.case.status
        assert_transition(from_status, to_status)
        state.errors.append(CaseError(
            code=f"STEP_FAILED:{step.name}",
            message=error_msg,
            path=step.name,
            recoverable=to_status == CaseStatus.PARTIAL,
        ))
        state.trace.append(TraceEvent(
            event=f"step_failed:{step.name}",
            step=step.name,
            detail={"from": from_status.value, "to": to_status.value, "error": error_msg},
        ))
        self._store.save_checkpoint(state.case.id, from_status, to_status, state)
        return state

    def _emit(self, callback, data):
        if callback:
            try:
                callback(data)
            except Exception:
                pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
