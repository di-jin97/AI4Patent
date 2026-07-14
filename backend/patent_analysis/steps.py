"""Safe baseline steps for the structured IDEA-review workflow.

These steps establish a persisted, inspectable case pipeline.  They deliberately
leave novelty/inventiveness as ``uncertain`` until a later feature/evidence
extractor can supply verified claim-level evidence; search snippets alone are
not a valid legal conclusion.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .adapters.base import SearchProvider, SearchRequest
from .domain.models import (
    Artifact,
    CaseStatus,
    CommercialValueResult,
    Feature,
    InventiveStepResult,
    NoveltyEvaluationResult,
    PriorArtDocument,
    Query,
    SearchPlan,
    SearchRun,
    TraceEvent,
)
from .domain.ids import IDGenerator
from .services.documents import deduplicate_documents, rank_documents
from .services.quality import run_quality_gate
from .workflow.orchestrator import WorkflowStep


class _Step(WorkflowStep):
    def __init__(self, name: str, start: CaseStatus, target: CaseStatus) -> None:
        self.name = name
        self.allowed_from = frozenset({start})
        self.target = target


class IntakeStep(_Step):
    def __init__(self) -> None:
        super().__init__("intake", CaseStatus.CREATED, CaseStatus.INTAKE_PARSED)

    async def run(self, state):
        state.invention = {"summary": state.request.idea.strip()}
        return state


class FeatureExtractionStep(_Step):
    def __init__(self) -> None:
        super().__init__("feature_extraction", CaseStatus.INTAKE_PARSED, CaseStatus.FEATURES_EXTRACTED)

    async def run(self, state):
        # A conservative deterministic baseline: one feature for each meaningful
        # clause.  The future LLM parser may refine these records, but it must not
        # rewrite their stable identifiers.
        fragments = [part.strip() for part in _split_idea(state.request.idea) if len(part.strip()) >= 4]
        generator = IDGenerator()
        state.features = [
            Feature(id=generator.next("F"), text=fragment, kind="necessary")
            for fragment in fragments[:12]
        ] or [Feature(id="F-001", text=state.request.idea.strip(), kind="necessary")]
        return state


class SearchPlanningStep(_Step):
    def __init__(self) -> None:
        super().__init__("search_planning", CaseStatus.FEATURES_EXTRACTED, CaseStatus.SEARCH_PLANNED)

    async def run(self, state):
        query_text = " ".join(feature.text for feature in state.features[:4]).strip()
        query = Query(id="Q-001", query_text=query_text, language="zh" if _contains_cjk(query_text) else "en")
        state.queries = [query]
        state.search_plan = SearchPlan(queries=[query], phases={"A": [query.id]}, strategy="baseline feature query")
        return state


class SearchStartedStep(_Step):
    def __init__(self) -> None:
        super().__init__("search_started", CaseStatus.SEARCH_PLANNED, CaseStatus.SEARCHING)

    async def run(self, state):
        return state


class SearchExecutionStep(_Step):
    def __init__(self, provider: SearchProvider) -> None:
        super().__init__("search_execution", CaseStatus.SEARCHING, CaseStatus.SEARCH_COMPLETED)
        self.provider = provider

    async def run(self, state):
        documents: list[PriorArtDocument] = []
        for query in state.queries:
            response = await self.provider.search(SearchRequest(
                request_id=f"{state.case.id}:{query.id}",
                query=query.query_text,
                language=query.language,
                phase=query.phase,
                types=query.types,
                limit=min(query.limit, state.budget.max_documents),
                idempotency_key=f"{state.case.id}:{query.id}:search",
            ))
            state.search_runs.append(SearchRun(
                query_id=query.id,
                idempotency_key=response.idempotency_key or f"{state.case.id}:{query.id}:search",
                provider=response.provider,
                result_count=len(response.results),
                status="success" if response.status == "success" else "failed",
                error=response.error,
            ))
            if response.status != "success":
                raise RuntimeError(response.error or f"Search provider {response.provider} failed")
            query.executed = True
            for result in response.results:
                documents.append(PriorArtDocument(
                    id=f"DOC-{len(documents) + 1:03d}",
                    type="patent" if "patent" in result.url.lower() else "web",
                    title=result.title,
                    publication_number=result.publication_number,
                    publication_date=result.published_date,
                    abstract=result.snippet,
                    source_url=result.url,
                    source_provider=response.provider,
                ))
        state.documents = deduplicate_documents(documents)[:state.budget.max_documents]
        return state


class DocumentRankingStep(_Step):
    def __init__(self) -> None:
        super().__init__("document_ranking", CaseStatus.SEARCH_COMPLETED, CaseStatus.DOCUMENTS_RANKED)

    async def run(self, state):
        state.ranking = rank_documents(state.documents, [feature.text for feature in state.features])
        return state


class FullTextDeferredStep(_Step):
    def __init__(self) -> None:
        super().__init__("fulltext_deferred", CaseStatus.DOCUMENTS_RANKED, CaseStatus.FULLTEXT_FETCHED)

    async def run(self, state):
        state.trace.append(TraceEvent(
            event="fulltext_deferred",
            step=self.name,
            detail={"reason": "Beta workflow does not treat search snippets as verified evidence"},
        ))
        return state


class EvidenceDeferredStep(_Step):
    def __init__(self) -> None:
        super().__init__("evidence_deferred", CaseStatus.FULLTEXT_FETCHED, CaseStatus.EVIDENCE_EXTRACTED)

    async def run(self, state):
        return state


class NoveltyUncertainStep(_Step):
    def __init__(self) -> None:
        super().__init__("novelty_evaluation", CaseStatus.EVIDENCE_EXTRACTED, CaseStatus.NOVELTY_EVALUATED)

    async def run(self, state):
        state.novelty = NoveltyEvaluationResult(overall="uncertain")
        return state


class InventivenessUncertainStep(_Step):
    def __init__(self) -> None:
        super().__init__("inventiveness_evaluation", CaseStatus.NOVELTY_EVALUATED, CaseStatus.INVENTIVENESS_EVALUATED)

    async def run(self, state):
        state.inventiveness = InventiveStepResult(overall="uncertain")
        return state


class CommercialValueStep(_Step):
    def __init__(self) -> None:
        super().__init__("commercial_value", CaseStatus.INVENTIVENESS_EVALUATED, CaseStatus.COMMERCIAL_VALUE_EVALUATED)

    async def run(self, state):
        state.commercial_value = CommercialValueResult(overall_confidence=0.0)
        return state


class QualityStep(_Step):
    def __init__(self) -> None:
        super().__init__("quality_gate", CaseStatus.COMMERCIAL_VALUE_EVALUATED, CaseStatus.QUALITY_VALIDATED)

    async def run(self, state):
        state.quality = run_quality_gate(state)
        return state


class ReportStep(_Step):
    def __init__(self, cases_root: Path) -> None:
        super().__init__("report", CaseStatus.QUALITY_VALIDATED, CaseStatus.REPORT_RENDERED)
        self.cases_root = cases_root

    async def run(self, state):
        self._write_report(state)
        return state

    def _write_report(self, state) -> None:
        artifact_dir = self.cases_root / state.case.id / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / "idea-review-beta.md"
        content = _render_markdown(state)
        path.write_text(content, encoding="utf-8")
        state.artifacts = [Artifact(
            name=path.name,
            format="markdown",
            path=str(path),
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            state_revision=state.case.revision,
        )]


class PartialReportStep(ReportStep):
    def __init__(self, cases_root: Path) -> None:
        super().__init__(cases_root)
        self.name = "partial_report"
        self.allowed_from = frozenset({CaseStatus.PARTIAL})


class CompleteStep(_Step):
    def __init__(self) -> None:
        super().__init__("complete", CaseStatus.REPORT_RENDERED, CaseStatus.COMPLETED)

    async def run(self, state):
        return state


def build_default_steps(provider: SearchProvider, cases_root: Path) -> list[WorkflowStep]:
    return [
        IntakeStep(), FeatureExtractionStep(), SearchPlanningStep(), SearchStartedStep(),
        SearchExecutionStep(provider), DocumentRankingStep(), FullTextDeferredStep(),
        EvidenceDeferredStep(), NoveltyUncertainStep(), InventivenessUncertainStep(),
        CommercialValueStep(), QualityStep(), ReportStep(cases_root), PartialReportStep(cases_root), CompleteStep(),
    ]


def _split_idea(idea: str) -> list[str]:
    import re
    return re.split(r"[。；;\n]+", idea)


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _render_markdown(state) -> str:
    documents = "\n".join(
        f"- {doc.title or '未命名文献'}：{doc.source_url or '无链接'}"
        for doc in state.documents
    ) or "- 本次检索未返回候选文献。"
    return f"""# 专利 IDEA 结构化评审（Beta）

> 本报告仅完成结构化检索基线。尚无经核验的权利要求/段落证据，因此新颖性和创造性结论均为“不确定”，不能替代专业检索或法律意见。

## Idea

{state.request.idea}

## 技术特征

""" + "\n".join(f"- {feature.id}: {feature.text}" for feature in state.features) + f"""

## 候选文献

{documents}

## 当前结论

- 新颖性：{state.novelty.overall if state.novelty else 'uncertain'}
- 创造性：{state.inventiveness.overall if state.inventiveness else 'uncertain'}
- 质量门：{'通过' if state.quality and state.quality.passed else '存在告警'}
"""
