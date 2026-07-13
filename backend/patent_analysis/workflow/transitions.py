"""State transition rules.

按 design doc Section 5.1 定义的状态机迁移规则。
"""

from __future__ import annotations

from ..domain.models import CaseStatus

_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.CREATED: {
        CaseStatus.INTAKE_PARSED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.INTAKE_PARSED: {
        CaseStatus.FEATURES_EXTRACTED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.FEATURES_EXTRACTED: {
        CaseStatus.SEARCH_PLANNED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.SEARCH_PLANNED: {
        CaseStatus.SEARCHING,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.SEARCHING: {
        CaseStatus.SEARCH_COMPLETED,
        CaseStatus.PARTIAL,
        CaseStatus.CANCELLED,
        CaseStatus.FAILED,
    },
    CaseStatus.SEARCH_COMPLETED: {
        CaseStatus.DOCUMENTS_RANKED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.DOCUMENTS_RANKED: {
        CaseStatus.FULLTEXT_FETCHED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.FULLTEXT_FETCHED: {
        CaseStatus.EVIDENCE_EXTRACTED,
        CaseStatus.PARTIAL,
        CaseStatus.CANCELLED,
        CaseStatus.FAILED,
    },
    CaseStatus.EVIDENCE_EXTRACTED: {
        CaseStatus.NOVELTY_EVALUATED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.NOVELTY_EVALUATED: {
        CaseStatus.INVENTIVENESS_EVALUATED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.INVENTIVENESS_EVALUATED: {
        CaseStatus.COMMERCIAL_VALUE_EVALUATED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.COMMERCIAL_VALUE_EVALUATED: {
        CaseStatus.QUALITY_VALIDATED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.QUALITY_VALIDATED: {
        CaseStatus.REPORT_RENDERED,
        CaseStatus.PARTIAL,
        CaseStatus.FAILED,
    },
    CaseStatus.REPORT_RENDERED: {
        CaseStatus.COMPLETED,
        CaseStatus.FAILED,
    },
    CaseStatus.PARTIAL: {
        CaseStatus.REPORT_RENDERED,
        CaseStatus.FAILED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.CANCELLED: set(),
    CaseStatus.COMPLETED: set(),
    CaseStatus.FAILED: set(),
}


def can_transition(from_status: CaseStatus, to_status: CaseStatus) -> bool:
    return to_status in _TRANSITIONS.get(from_status, set())


def assert_transition(from_status: CaseStatus, to_status: CaseStatus) -> None:
    if not can_transition(from_status, to_status):
        raise ValueError(f"INVALID_TRANSITION: {from_status.value} -> {to_status.value}")


def allowed_from(status: CaseStatus) -> frozenset[CaseStatus]:
    """返回可从此状态转移到的目标状态集合"""
    return frozenset(_TRANSITIONS.get(status, set()))


def is_terminal(status: CaseStatus) -> bool:
    return status in {
        CaseStatus.CANCELLED,
        CaseStatus.COMPLETED,
        CaseStatus.FAILED,
    }
