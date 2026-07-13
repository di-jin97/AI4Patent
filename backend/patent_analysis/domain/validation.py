"""Evidence, Date and Quality Gate validators.

按 design doc Section 6.3, 7.3 要求，所有确定性法律模拟结论必须可追溯至证据。
No Evidence → No Legal Conclusion.

Quality Gate 必须拦截:
- 无有效 Evidence 的确定性结论
- 晚于 priority_date 却作为现有技术
- 未经验证 URL
- 声称已核实但证据缺失
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import EvidenceItem, PriorArtDocument
from .dates import is_valid_prior_art, parse_date


@dataclass
class QualityGateIssue:
    code: str
    path: str
    message: str


@dataclass
class EvidenceValidator:
    name: str = "evidence-validator"

    def validate(self, evidence: EvidenceItem, *, require_location: bool = True) -> list[QualityGateIssue]:
        issues: list[QualityGateIssue] = []
        path = f"evidence.{evidence.id}"

        if evidence.verified and not evidence.has_source_url() and evidence.source_type != "user-input":
            issues.append(QualityGateIssue(
                "EVIDENCE_VERIFIED_NO_URL",
                path,
                f"Verified evidence {evidence.id} missing source_url"
            ))

        if evidence.verified and not evidence.has_quoted_text():
            issues.append(QualityGateIssue(
                "EVIDENCE_VERIFIED_NO_QUOTE",
                path,
                f"Verified evidence {evidence.id} missing quoted_text"
            ))

        if require_location and not evidence.has_location():
            issues.append(QualityGateIssue(
                "EVIDENCE_NO_LOCATION",
                path,
                f"Evidence {evidence.id} has no location field (claim/paragraph/page/section)"
            ))

        if evidence.confidence < 0.3:
            issues.append(QualityGateIssue(
                "EVIDENCE_LOW_CONFIDENCE",
                path,
                f"Evidence {evidence.id} has low confidence ({evidence.confidence})"
            ))

        if evidence.verified and evidence.verification_method is None:
            issues.append(QualityGateIssue(
                "EVIDENCE_NO_VERIFICATION_METHOD",
                path,
                f"Verified evidence {evidence.id} missing verification_method"
            ))

        return issues

    def is_sufficient_for_conclusion(self, evidence: EvidenceItem) -> bool:
        return (
            evidence.verified
            and evidence.has_location()
            and evidence.has_quoted_text()
            and evidence.confidence >= 0.5
        )


@dataclass
class DateValidator:
    name: str = "date-validator"

    def validate(self, document: PriorArtDocument, priority_date: str | None) -> list[QualityGateIssue]:
        issues: list[QualityGateIssue] = []
        path = f"document.{document.id}"

        if not priority_date:
            return issues

        if not document.publication_date:
            issues.append(QualityGateIssue(
                "DATE_MISSING",
                path,
                f"Document {document.id} missing publication_date"
            ))
            return issues

        if not is_valid_prior_art(document.publication_date, priority_date):
            issues.append(QualityGateIssue(
                "DATE_POST_PRIORITY",
                path,
                f"Document {document.id} publication_date ({document.publication_date}) "
                f"is after priority_date ({priority_date})"
            ))

        return issues

    def is_valid_prior_art(self, document: PriorArtDocument, priority_date: str | None) -> bool:
        if not document.publication_date or not priority_date:
            return False
        return is_valid_prior_art(document.publication_date, priority_date)


@dataclass
class FeatureCoverageValidator:
    name: str = "feature-coverage-validator"

    def validate(
        self,
        feature_ids: list[str],
        evidence_feature_map: dict[str, list[str]],
        *, require_complete: bool = True,
    ) -> list[QualityGateIssue]:
        issues: list[QualityGateIssue] = []
        all_covered: set[str] = set()

        for ev_id, f_ids in evidence_feature_map.items():
            for fid in f_ids:
                all_covered.add(fid)

        uncovered = set(feature_ids) - all_covered
        required = {f for f in feature_ids}  # caller should filter necessary vs optional

        missing_required = required - all_covered
        if missing_required:
            issues.append(QualityGateIssue(
                "FEATURE_UNCOVERED",
                "features",
                f"Necessary features not covered by evidence: {sorted(missing_required)}"
            ))

        return issues


@dataclass
class QualityGate:
    name: str = "quality-gate"
    evidence_validator: EvidenceValidator = field(default_factory=EvidenceValidator)
    date_validator: DateValidator = field(default_factory=DateValidator)
    coverage_validator: FeatureCoverageValidator = field(default_factory=FeatureCoverageValidator)

    def run(
        self,
        evidence_list: list[EvidenceItem],
        documents: dict[str, PriorArtDocument],
        features_necessary: list[str],
        priority_date: str | None,
        conclusion_ids: list[str],
    ) -> tuple[list[QualityGateIssue], list[QualityGateIssue], list[str]]:
        errors: list[QualityGateIssue] = []
        warnings: list[QualityGateIssue] = []
        blocked: list[str] = []

        doc_map = {d.id: d for d in documents.values()}

        for ev in evidence_list:
            for issue in self.evidence_validator.validate(ev):
                if issue.code in ("EVIDENCE_NO_LOCATION", "EVIDENCE_VERIFIED_NO_URL"):
                    errors.append(issue)
                else:
                    warnings.append(issue)

            if ev.document_id in doc_map:
                doc = doc_map[ev.document_id]
                for issue in self.date_validator.validate(doc, priority_date):
                    errors.append(issue)

        evidence_feature_map: dict[str, list[str]] = {}
        for ev in evidence_list:
            evidence_feature_map[ev.id] = ev.feature_ids

        for issue in self.coverage_validator.validate(
            features_necessary, evidence_feature_map, require_complete=True
        ):
            errors.append(issue)

        for cid in conclusion_ids:
            evidence_for_conclusion = [ev for ev in evidence_list if ev.supports and any(
                cid in s for s in ev.supports
            )]
            if not evidence_for_conclusion:
                blocked.append(cid)
                errors.append(QualityGateIssue(
                    "CONCLUSION_NO_EVIDENCE",
                    f"conclusion.{cid}",
                    f"Conclusion {cid} has no supporting evidence"
                ))
                continue

            for ev in evidence_for_conclusion:
                if ev.document_id in doc_map:
                    doc = doc_map[ev.document_id]
                    if not self.date_validator.is_valid_prior_art(doc, priority_date):
                        blocked.append(cid)
                        errors.append(QualityGateIssue(
                            "CONCLUSION_INVALID_DOCUMENT",
                            f"conclusion.{cid}",
                            f"Conclusion {cid} relies on document {ev.document_id} "
                            f"which is not valid prior art"
                        ))
                        break

            sufficient = any(
                self.evidence_validator.is_sufficient_for_conclusion(ev)
                for ev in evidence_for_conclusion
            )
            if not sufficient:
                blocked.append(cid)
                errors.append(QualityGateIssue(
                    "CONCLUSION_INSUFFICIENT_EVIDENCE",
                    f"conclusion.{cid}",
                    f"Conclusion {cid} evidence is insufficient (no verified, located, quoted evidence)"
                ))

        return errors, warnings, blocked
