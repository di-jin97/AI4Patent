"""Quality gate service.

按 design doc Section 7.3 定义：拦截无证据/无效日期的确定性结论。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..domain.models import (
    EvidenceItem,
    Feature,
    PatentCaseState,
    PriorArtDocument,
    QualityGateResult,
)
from ..domain.dates import is_valid_prior_art
from ..domain.validation import (
    EvidenceValidator,
    DateValidator,
    FeatureCoverageValidator,
    QualityGateIssue,
)


def run_quality_gate(state: PatentCaseState) -> QualityGateResult:
    """对冻结的 State 运行质量门校验。

    返回 QualityGateResult:
    - passed=True: 无 error，可继续渲染
    - errors: 阻断性错误列表
    - warnings: 非阻断警告
    - blocked_conclusion_ids: 被阻断的结论 ID
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    blocked: list[str] = []

    ev_validator = EvidenceValidator()
    date_validator = DateValidator()

    for ev in state.evidence:
        issues = ev_validator.validate(ev, require_location=True)
        for issue in issues:
            if issue.code in ("EVIDENCE_NO_LOCATION", "EVIDENCE_VERIFIED_NO_URL",
                              "EVIDENCE_NO_VERIFICATION_METHOD"):
                errors.append(_to_dict(issue))
            else:
                warnings.append(_to_dict(issue))

    for ev in state.evidence:
        if not ev.verified and not ev.has_location():
            continue
        doc = _find_doc(state.documents, ev.document_id)
        if doc:
            issues = date_validator.validate(doc, state.priority_date)
            for issue in issues:
                errors.append(_to_dict(issue))

    if state.novelty and state.novelty.overall == "not-novel":
        necessary_ids = [f.id for f in state.features if f.kind == "necessary"]
        covered: set[str] = set()
        for ev in state.evidence:
            if ev.verified and ev.has_location():
                for fid in ev.feature_ids:
                    covered.add(fid)

        missing = set(necessary_ids) - covered
        if missing:
            errors.append({
                "code": "NOVELTY_UNCOVERED_FEATURES",
                "path": "novelty",
                "message": f"Novelty conclusion is 'not-novel' but features {sorted(missing)} have no verified evidence",
            })

    if state.novelty and state.novelty.overall == "not-novel":
        doc_ids_used = set(
            ev.document_id for ev in state.evidence
            if ev.verified and ev.has_location()
        )
        for doc in state.documents:
            if doc.id in doc_ids_used:
                if not is_valid_prior_art(doc.publication_date, state.priority_date):
                    errors.append({
                        "code": "NOVELTY_INVALID_DATE",
                        "path": f"documents.{doc.id}",
                        "message": f"Document {doc.id} used in 'not-novel' conclusion has invalid date",
                    })

    novelty_blocked = any(
        e.get("code", "").startswith("NOVELTY_")
        for e in errors
    )
    if novelty_blocked and state.novelty:
        blocked.append("novelty:overall")

    passed = len(errors) == 0

    return QualityGateResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        blocked_conclusion_ids=blocked,
    )


def _find_doc(documents: list[PriorArtDocument], doc_id: str) -> PriorArtDocument | None:
    for d in documents:
        if d.id == doc_id:
            return d
    return None


def _to_dict(issue: QualityGateIssue) -> dict[str, str]:
    return {"code": issue.code, "path": issue.path, "message": issue.message}
