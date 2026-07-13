"""Budget management.

按 design doc Section 4 和 7.4 定义的预算控制系统。
"""

from __future__ import annotations

from ..domain.models import ExecutionBudget
from ..domain.models import MODES

_DEFAULT_BUDGETS: dict[str, ExecutionBudget] = {
    "quick": ExecutionBudget(
        max_search_calls=6,
        max_fetch_calls=6,
        max_documents=24,
        max_full_text_documents=4,
        max_tokens=80_000,
        max_workflow_duration_seconds=600,
        max_retries_per_tool=1,
        max_d1_routes=1,
        max_d2_per_feature=1,
    ),
    "standard": ExecutionBudget(
        max_search_calls=16,
        max_fetch_calls=16,
        max_documents=60,
        max_full_text_documents=12,
        max_tokens=160_000,
        max_workflow_duration_seconds=1_800,
        max_retries_per_tool=2,
        max_d1_routes=3,
        max_d2_per_feature=2,
    ),
    "deep": ExecutionBudget(
        max_search_calls=36,
        max_fetch_calls=35,
        max_documents=120,
        max_full_text_documents=28,
        max_tokens=320_000,
        max_workflow_duration_seconds=3_600,
        max_retries_per_tool=3,
        max_d1_routes=5,
        max_d2_per_feature=3,
    ),
    "commercial": ExecutionBudget(
        max_search_calls=12,
        max_fetch_calls=12,
        max_documents=40,
        max_full_text_documents=10,
        max_tokens=128_000,
        max_workflow_duration_seconds=1_200,
        max_retries_per_tool=2,
        max_d1_routes=2,
        max_d2_per_feature=2,
    ),
}


def get_mode_budget(mode: str) -> ExecutionBudget:
    """获取指定模式的默认预算配置"""
    return _DEFAULT_BUDGETS.get(mode, _DEFAULT_BUDGETS["standard"])


class BudgetExhaustedError(Exception):
    def __init__(self, kind: str):
        self.kind = kind
        super().__init__(f"BUDGET_EXHAUSTED: {kind}")


class BudgetManager:
    """预算管理器，追踪消耗并阻止超额"""

    def __init__(self, budget: ExecutionBudget) -> None:
        self.budget = budget

    def reserve(self, kind: str, amount: int = 1) -> int:
        """预留指定数量的预算，超额抛出 BudgetExhaustedError"""
        limits: dict[str, int] = {
            "searchCalls": self.budget.max_search_calls,
            "fetchCalls": self.budget.max_fetch_calls,
            "documents": self.budget.max_documents,
            "fullTextDocuments": self.budget.max_full_text_documents,
            "tokens": self.budget.max_tokens,
            "retries": self.budget.max_retries_per_tool,
            "d1Routes": self.budget.max_d1_routes,
            "d2PerFeature": self.budget.max_d2_per_feature,
        }
        limit = limits.get(kind, 1_000_000)
        consumed = self.budget.consumed.get(kind, 0)
        if consumed + amount > limit:
            raise BudgetExhaustedError(kind)
        self.budget.consumed[kind] = consumed + amount
        return self.budget.consumed[kind]

    def can_reserve(self, kind: str, amount: int = 1) -> bool:
        try:
            self.reserve(kind, amount)
            self.budget.consumed[kind] = self.budget.consumed.get(kind, 0) - amount
            return True
        except BudgetExhaustedError:
            return False

    def remaining(self, kind: str) -> int:
        limits: dict[str, int] = {
            "searchCalls": self.budget.max_search_calls,
            "fetchCalls": self.budget.max_fetch_calls,
            "documents": self.budget.max_documents,
            "fullTextDocuments": self.budget.max_full_text_documents,
            "tokens": self.budget.max_tokens,
        }
        return max(0, limits.get(kind, 0) - self.budget.consumed.get(kind, 0))

    def is_exhausted(self, kind: str) -> bool:
        return self.remaining(kind) <= 0
