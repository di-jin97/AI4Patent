"""SQLite-based state store.

按 design doc Section 10.1 定义：存储案件元数据、revision、状态迁移、
请求和缓存索引；大文本存 workspace/cases/<caseId>/artifacts/。
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..domain.models import (
    CaseMeta,
    CaseRequest,
    CaseStatus,
    ExecutionBudget,
    PatentCaseState,
)
from ..workflow.transitions import assert_transition, is_terminal


_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'CREATED',
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'standard',
    priority_date TEXT,
    jurisdiction TEXT NOT NULL DEFAULT '["CN"]',
    request_json TEXT NOT NULL DEFAULT '{}',
    features_json TEXT NOT NULL DEFAULT '[]',
    documents_json TEXT NOT NULL DEFAULT '[]',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    novelty_json TEXT,
    inventiveness_json TEXT,
    commercial_value_json TEXT,
    quality_json TEXT,
    budget_json TEXT NOT NULL DEFAULT '{}',
    errors_json TEXT NOT NULL DEFAULT '[]',
    full_state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key_hash TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    result TEXT,
    consumed_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_case ON checkpoints(case_id, revision);
CREATE INDEX IF NOT EXISTS idx_idempotency_case ON idempotency_keys(case_id);
"""


class StateStore:
    """案件状态持久化存储"""

    def __init__(self, db_path: str | Path = "workspace/cases/patent_cases.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_DDL)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def create_case(self, state: PatentCaseState) -> PatentCaseState:
        state.case.revision = 0
        state.case.status = CaseStatus.CREATED
        state.case.updated_at = _now()

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO cases (id, status, revision, created_at, updated_at, mode,
                   priority_date, jurisdiction, request_json, features_json,
                   documents_json, evidence_json, budget_json, full_state_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    state.case.id,
                    state.case.status.value,
                    state.case.revision,
                    state.case.created_at,
                    state.case.updated_at,
                    state.mode,
                    state.priority_date,
                    json.dumps(state.jurisdiction, ensure_ascii=False),
                    state.request.model_dump_json(),
                    _serialize_list(state.features),
                    _serialize_list(state.documents),
                    _serialize_list(state.evidence),
                    state.budget.model_dump_json(),
                    state.model_dump_json(),
                ),
            )
            conn.commit()

        return state

    def load_case(self, case_id: str) -> PatentCaseState | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_state(row)

    def _row_to_state(self, row: sqlite3.Row) -> PatentCaseState:
        data = json.loads(row["full_state_json"])
        data["case"]["status"] = row["status"]
        data["case"]["revision"] = row["revision"]
        data["case"]["updated_at"] = row["updated_at"]
        data["case"]["created_at"] = row["created_at"]
        return PatentCaseState.model_validate(data)

    def save_checkpoint(self, case_id: str, from_status: CaseStatus,
                        to_status: CaseStatus, state: PatentCaseState) -> int:
        assert_transition(from_status, to_status)

        new_revision = state.case.revision + 1
        state.case.revision = new_revision
        state.case.status = to_status
        state.case.updated_at = _now()

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO checkpoints (case_id, revision, from_status, to_status,
                   checkpoint_json, created_at) VALUES (?,?,?,?,?,?)""",
                (case_id, new_revision, from_status.value, to_status.value,
                 state.model_dump_json(), _now()),
            )
            conn.execute(
                """UPDATE cases SET status=?, revision=?, updated_at=?,
                   features_json=?, documents_json=?, evidence_json=?,
                   novelty_json=?, inventiveness_json=?, commercial_value_json=?,
                   quality_json=?, budget_json=?, errors_json=?, full_state_json=?
                   WHERE id=?""",
                (
                    to_status.value,
                    new_revision,
                    state.case.updated_at,
                    _serialize_list(state.features),
                    _serialize_list(state.documents),
                    _serialize_list(state.evidence),
                    state.novelty.model_dump_json() if state.novelty else None,
                    state.inventiveness.model_dump_json() if state.inventiveness else None,
                    state.commercial_value.model_dump_json() if state.commercial_value else None,
                    state.quality.model_dump_json() if state.quality else None,
                    state.budget.model_dump_json(),
                    json.dumps([e.model_dump() for e in state.errors], ensure_ascii=False),
                    state.model_dump_json(),
                    case_id,
                ),
            )
            conn.commit()

        return new_revision

    def last_checkpoint(self, case_id: str) -> PatentCaseState | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM checkpoints WHERE case_id=?
                   ORDER BY revision DESC LIMIT 1""",
                (case_id,),
            ).fetchone()
            if row is None:
                row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
                if row is None:
                    return None
                return self._row_to_state(row)
            return PatentCaseState.model_validate(json.loads(row["checkpoint_json"]))

    def check_idempotency(self, key: str) -> str | None:
        """检查幂等键，返回已有结果或 None"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT result FROM idempotency_keys WHERE key_hash=?",
                (_hash_key(key),),
            ).fetchone()
            return row["result"] if row else None

    def record_idempotency(self, case_id: str, key: str, result: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO idempotency_keys (key_hash, case_id, result, consumed_at)
                   VALUES (?,?,?,?)""",
                (_hash_key(key), case_id, result, _now()),
            )
            conn.commit()

    def list_cases(self, status: str | None = None) -> list[str]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT id FROM cases WHERE status=? ORDER BY updated_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM cases ORDER BY updated_at DESC"
                ).fetchall()
            return [r["id"] for r in rows]

    def cancel_case(self, case_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()
            if row is None:
                return False
            current = CaseStatus(row["status"])
            if is_terminal(current):
                return True
            conn.execute(
                "UPDATE cases SET status=? WHERE id=?",
                (CaseStatus.CANCELLED.value, case_id),
            )
            conn.commit()
            return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_key(key: str) -> str:
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()


def _serialize_list(items) -> str:
    return json.dumps(
        [i.model_dump() for i in items],
        ensure_ascii=False,
    )
