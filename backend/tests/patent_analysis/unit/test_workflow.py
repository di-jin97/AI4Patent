"""Unit tests for workflow: transitions, budget, state store.

按 design doc Section 12.1 定义。
"""

import json
import os
import tempfile
import uuid
import pytest

from backend.patent_analysis.domain.models import (
    CaseStatus,
    PatentCaseState,
    CaseMeta,
    CaseRequest,
    ExecutionBudget,
    Feature,
    CaseError,
)
from backend.patent_analysis.workflow.transitions import (
    can_transition,
    assert_transition,
    allowed_from,
    is_terminal,
)
from backend.patent_analysis.workflow.budget import (
    BudgetManager,
    BudgetExhaustedError,
    get_mode_budget,
)
from backend.patent_analysis.persistence.state_store import StateStore


# ─── Transitions ──────────────────────────────────────────────────────

class TestTransitions:
    def test_valid_creation_to_intake(self):
        assert can_transition(CaseStatus.CREATED, CaseStatus.INTAKE_PARSED)

    def test_valid_feature_to_search(self):
        assert can_transition(CaseStatus.FEATURES_EXTRACTED, CaseStatus.SEARCH_PLANNED)

    def test_invalid_skip(self):
        assert not can_transition(CaseStatus.CREATED, CaseStatus.SEARCHING)

    def test_assert_valid(self):
        assert_transition(CaseStatus.CREATED, CaseStatus.INTAKE_PARSED)

    def test_assert_invalid(self):
        with pytest.raises(ValueError, match="INVALID_TRANSITION"):
            assert_transition(CaseStatus.CREATED, CaseStatus.SEARCHING)

    def test_terminal_states(self):
        assert is_terminal(CaseStatus.COMPLETED)
        assert is_terminal(CaseStatus.FAILED)
        assert is_terminal(CaseStatus.CANCELLED)
        assert not is_terminal(CaseStatus.CREATED)

    def test_allowed_from_created(self):
        allowed = allowed_from(CaseStatus.CREATED)
        assert CaseStatus.INTAKE_PARSED in allowed
        assert CaseStatus.FAILED in allowed
        assert CaseStatus.CANCELLED in allowed

    def test_complete_valid_path(self):
        path = [
            (CaseStatus.CREATED, CaseStatus.INTAKE_PARSED),
            (CaseStatus.INTAKE_PARSED, CaseStatus.FEATURES_EXTRACTED),
            (CaseStatus.FEATURES_EXTRACTED, CaseStatus.SEARCH_PLANNED),
            (CaseStatus.SEARCH_PLANNED, CaseStatus.SEARCHING),
            (CaseStatus.SEARCHING, CaseStatus.SEARCH_COMPLETED),
            (CaseStatus.SEARCH_COMPLETED, CaseStatus.DOCUMENTS_RANKED),
            (CaseStatus.DOCUMENTS_RANKED, CaseStatus.FULLTEXT_FETCHED),
            (CaseStatus.FULLTEXT_FETCHED, CaseStatus.EVIDENCE_EXTRACTED),
            (CaseStatus.EVIDENCE_EXTRACTED, CaseStatus.NOVELTY_EVALUATED),
            (CaseStatus.NOVELTY_EVALUATED, CaseStatus.INVENTIVENESS_EVALUATED),
            (CaseStatus.INVENTIVENESS_EVALUATED, CaseStatus.COMMERCIAL_VALUE_EVALUATED),
            (CaseStatus.COMMERCIAL_VALUE_EVALUATED, CaseStatus.QUALITY_VALIDATED),
            (CaseStatus.QUALITY_VALIDATED, CaseStatus.REPORT_RENDERED),
            (CaseStatus.REPORT_RENDERED, CaseStatus.COMPLETED),
        ]
        for from_s, to_s in path:
            assert can_transition(from_s, to_s), f"Should allow {from_s}->{to_s}"


# ─── Budget ───────────────────────────────────────────────────────────

class TestBudgetManager:
    def test_reserve_search_calls(self):
        budget = ExecutionBudget(max_search_calls=10, max_tokens=100)
        mgr = BudgetManager(budget)
        assert mgr.reserve("searchCalls", 3) == 3
        assert budget.consumed["searchCalls"] == 3

    def test_exhausted(self):
        budget = ExecutionBudget(max_search_calls=3)
        mgr = BudgetManager(budget)
        mgr.reserve("searchCalls", 3)
        with pytest.raises(BudgetExhaustedError, match="searchCalls"):
            mgr.reserve("searchCalls", 1)

    def test_can_reserve(self):
        budget = ExecutionBudget(max_search_calls=3)
        mgr = BudgetManager(budget)
        assert mgr.can_reserve("searchCalls", 3)
        assert mgr.can_reserve("searchCalls", 4) is False

    def test_remaining(self):
        budget = ExecutionBudget(max_search_calls=10)
        mgr = BudgetManager(budget)
        assert mgr.remaining("searchCalls") == 10
        mgr.reserve("searchCalls", 4)
        assert mgr.remaining("searchCalls") == 6

    def test_mode_budgets(self):
        quick = get_mode_budget("quick")
        assert quick.max_search_calls == 6

        standard = get_mode_budget("standard")
        assert standard.max_search_calls == 16

        deep = get_mode_budget("deep")
        assert deep.max_search_calls == 36

        commercial = get_mode_budget("commercial")
        assert commercial.max_search_calls == 12

    def test_unknown_mode_defaults_to_standard(self):
        unknown = get_mode_budget("unknown")
        assert unknown.max_search_calls == 16


# ─── State Store ──────────────────────────────────────────────────────

class TestStateStore:
    @pytest.fixture
    def store(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        s = StateStore(path)
        yield s
        s._conn().close()
        os.unlink(path)

    def _make_state(self, case_id: str, mode: str = "standard") -> PatentCaseState:
        return PatentCaseState(
            case=CaseMeta(id=case_id, status=CaseStatus.CREATED),
            request=CaseRequest(idea=f"Test idea for {case_id}"),
            mode=mode,
        )

    def test_create_and_load(self, store):
        state = self._make_state("case-001")
        created = store.create_case(state)
        assert created.case.id == "case-001"
        assert created.case.status == CaseStatus.CREATED

        loaded = store.load_case("case-001")
        assert loaded is not None
        assert loaded.case.id == "case-001"
        assert loaded.case.status == CaseStatus.CREATED

    def test_load_nonexistent(self, store):
        assert store.load_case("nonexistent") is None

    def test_save_checkpoint(self, store):
        state = self._make_state("case-002")
        store.create_case(state)

        state.case.status = CaseStatus.INTAKE_PARSED
        state.case.revision = 0
        rev = store.save_checkpoint(
            "case-002", CaseStatus.CREATED, CaseStatus.INTAKE_PARSED, state
        )
        assert rev == 1

        loaded = store.load_case("case-002")
        assert loaded.case.status == CaseStatus.INTAKE_PARSED
        assert loaded.case.revision == 1

    def test_last_checkpoint(self, store):
        state = self._make_state("case-003")
        store.create_case(state)

        state.features = [Feature(id="F-001", text="test", kind="necessary")]
        rev1 = store.save_checkpoint(
            "case-003", CaseStatus.CREATED, CaseStatus.INTAKE_PARSED, state
        )

        cp = store.last_checkpoint("case-003")
        assert cp is not None
        assert cp.case.status == CaseStatus.INTAKE_PARSED
        assert len(cp.features) == 1

    def test_invalid_transition_raises(self, store):
        state = self._make_state("case-004")
        store.create_case(state)
        with pytest.raises(ValueError, match="INVALID_TRANSITION"):
            store.save_checkpoint(
                "case-004", CaseStatus.CREATED, CaseStatus.SEARCHING, state
            )

    def test_idempotency(self, store):
        state = self._make_state("case-005")
        store.create_case(state)

        key = "test-key-001"
        assert store.check_idempotency(key) is None

        store.record_idempotency("case-005", key, "done")
        assert store.check_idempotency(key) == "done"

    def test_duplicate_idempotency_no_error(self, store):
        state = self._make_state("case-006")
        store.create_case(state)
        store.record_idempotency("case-006", "key-dup", "first")
        store.record_idempotency("case-006", "key-dup", "second")
        assert store.check_idempotency("key-dup") == "first"

    def test_list_cases(self, store):
        store.create_case(self._make_state("case-a"))
        store.create_case(self._make_state("case-b"))
        store.create_case(self._make_state("case-c"))
        cases = store.list_cases()
        assert len(cases) == 3

    def test_cancel_case(self, store):
        state = self._make_state("case-cancel")
        store.create_case(state)
        assert store.cancel_case("case-cancel") is True
        loaded = store.load_case("case-cancel")
        assert loaded.case.status == CaseStatus.CANCELLED

    def test_cancel_nonexistent(self, store):
        assert store.cancel_case("no-such-case") is False
