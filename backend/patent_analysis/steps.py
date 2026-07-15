"""Evidence-bound IDEA-review 1.0 workflow steps.

The legacy Skill's Step 0--6 capability is implemented as durable workflow
state.  Semantic work is delegated to small Skills; source retrieval and legal
gates stay deterministic and independently testable.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters.base import FetchRequest, SearchProvider, SearchRequest
from .domain.ids import IDGenerator
from .domain.models import (
    Artifact, CaseStatus, CommercialValueResult, EvidenceItem, Feature,
    FullTextRecord, InventiveStepResult, InventiveStepRoute,
    NoveltyEvaluationResult, PriorArtDocument, Query, SearchPlan, SearchRun,
    TraceEvent,
)
from .services.documents import deduplicate_documents, rank_documents
from .services.novelty import evaluate_novelty
from .services.quality import run_quality_gate
from .services.renderers import render_docx, render_xlsx
from .services.scorecard import build_idea_scorecard
from .skills.runner import SkillRunner, default_skill_runner
from .workflow.orchestrator import WorkflowStep


class _Step(WorkflowStep):
    def __init__(self, name: str, start: CaseStatus, target: CaseStatus) -> None:
        self.name, self.allowed_from, self.target = name, frozenset({start}), target


class IntakeStep(_Step):
    def __init__(self, runner: SkillRunner) -> None:
        super().__init__("intake", CaseStatus.CREATED, CaseStatus.INTAKE_PARSED)
        self.runner = runner

    async def run(self, state):
        parsed = await self.runner.run("patent-idea-intake", {"idea": state.request.idea, "mode": state.mode})
        state.invention = {"summary": state.request.idea.strip(), **parsed}
        return state


class FeatureExtractionStep(_Step):
    def __init__(self, runner: SkillRunner) -> None:
        super().__init__("feature_extraction", CaseStatus.INTAKE_PARSED, CaseStatus.FEATURES_EXTRACTED)
        self.runner = runner

    async def run(self, state):
        output = await self.runner.run("patent-feature-parser", {"idea": state.request.idea, "intake": state.invention})
        generator = IDGenerator()
        raw_features = output.get("features", [])
        state.features = [
            Feature(
                id=generator.next("F"), text=item["text"],
                kind=item["kind"], limitation=item["limitation"],
            )
            for item in (_normalize_feature(item) for item in raw_features)
            if item is not None
        ]
        if not state.features:
            state.features = [Feature(id="F-001", text=state.request.idea.strip(), kind="necessary")]
        state.claims = _normalize_claims(output.get("claims", []))
        state.invention["query_terms"] = _normalize_query_terms(output.get("query_terms", []))
        return state


class SearchPlanningStep(_Step):
    def __init__(self, runner: SkillRunner) -> None:
        super().__init__("search_planning", CaseStatus.FEATURES_EXTRACTED, CaseStatus.SEARCH_PLANNED)
        self.runner = runner

    async def run(self, state):
        output = await self.runner.run("patent-search-planner", {
            "idea": state.request.idea, "query_terms": state.invention.get("query_terms", []),
            "features": [{"id": item.id, "text": item.text} for item in state.features],
        })
        generator = IDGenerator()
        queries: list[Query] = []
        for item in output.get("queries", [])[:state.budget.max_search_calls]:
            if not isinstance(item, dict) or not str(item.get("query_text", "")).strip():
                continue
            phase = item.get("phase", "A")
            queries.append(Query(id=generator.next("Q"), query_text=str(item["query_text"]).strip(), language="zh" if _contains_cjk(str(item["query_text"])) else "en", phase=phase if phase in {"A", "B", "C", "D"} else "A", intent=str(item.get("intent", "")), types=["patent"], limit=min(20, state.budget.max_documents)))
        if not queries:
            text = " ".join(feature.text for feature in state.features[:4])
            queries = [Query(id="Q-001", query_text=text, language="zh" if _contains_cjk(text) else "en", types=["patent"])]
        state.queries = queries
        phases: dict[str, list[str]] = {}
        for query in queries:
            phases.setdefault(query.phase, []).append(query.id)
        state.search_plan = SearchPlan(queries=queries, phases=phases, strategy=str(output.get("strategy", "分批特征检索")))
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
            response = await self.provider.search(SearchRequest(request_id=f"{state.case.id}:{query.id}", query=query.query_text, language=query.language, phase=query.phase, types=query.types, limit=min(query.limit, state.budget.max_documents), idempotency_key=f"{state.case.id}:{query.id}:search"))
            state.search_runs.append(SearchRun(query_id=query.id, idempotency_key=response.idempotency_key or f"{state.case.id}:{query.id}:search", provider=response.provider, result_count=len(response.results), status="success" if response.status == "success" else "failed", error=response.error))
            if response.status not in {"success", "partial"}:
                raise RuntimeError(response.error or f"Search provider {response.provider} failed")
            query.executed = True
            for result in response.results:
                documents.append(PriorArtDocument(id=f"DOC-{len(documents) + 1:03d}", type="patent", title=result.title, publication_number=result.publication_number, publication_date=result.published_date, abstract=result.snippet, source_url=result.url, source_provider=response.provider))
        state.documents = deduplicate_documents(documents)[:state.budget.max_documents]
        return state


class DocumentRankingStep(_Step):
    def __init__(self) -> None:
        super().__init__("document_ranking", CaseStatus.SEARCH_COMPLETED, CaseStatus.DOCUMENTS_RANKED)

    async def run(self, state):
        state.ranking = rank_documents(state.documents, [feature.text for feature in state.features], priority_date=state.priority_date)
        return state


class FullTextFetchStep(_Step):
    def __init__(self, provider: SearchProvider) -> None:
        super().__init__("fulltext_fetch", CaseStatus.DOCUMENTS_RANKED, CaseStatus.FULLTEXT_FETCHED)
        self.provider = provider

    async def run(self, state):
        ranked = {item.document_id: item.fetch_priority for item in state.ranking}
        selected = sorted(state.documents, key=lambda item: ranked.get(item.id, 0), reverse=True)[:state.budget.max_full_text_documents]
        for doc in selected:
            if not doc.source_url:
                continue
            response = await self.provider.fetch(FetchRequest(request_id=f"{state.case.id}:{doc.id}:fulltext", urls=[doc.source_url], max_characters=100_000, idempotency_key=f"{state.case.id}:{doc.id}:fulltext"))
            result = response.results[0] if response.results else None
            content = result.content if result and result.status == "success" else ""
            status = "fetched" if content else "failed"
            state.full_text.append(FullTextRecord(document_id=doc.id, content_hash=hashlib.sha256(content.encode()).hexdigest(), url=doc.source_url, fetched_at=datetime.now(timezone.utc).isoformat(), status=status, content_preview=content[:2000], char_count=len(content), error=result.error if result else response.error))
            if content:
                doc.claims_text = content[:20_000]
                doc.content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                doc.source_raw["sections"] = _sections_from_content(content)
        return state


class EvidenceExtractionStep(_Step):
    def __init__(self, runner: SkillRunner) -> None:
        super().__init__("evidence_extraction", CaseStatus.FULLTEXT_FETCHED, CaseStatus.EVIDENCE_EXTRACTED)
        self.runner = runner

    async def run(self, state):
        # The Skill receives a bounded document slice.  Deterministic validation
        # below enforces quote/locator provenance even when a model is used.
        generator = IDGenerator()
        for doc in state.documents:
            sections = doc.source_raw.get("sections", [])
            if not sections:
                continue
            await self.runner.run("patent-evidence-extractor", {"document_id": doc.id, "features": [{"id": feature.id, "text": feature.text} for feature in state.features], "sections": sections[:80]})
            for feature in state.features:
                match = _find_feature_match(feature.text, sections)
                if not match:
                    continue
                locator, quoted = match
                state.evidence.append(EvidenceItem(id=generator.next("EV"), document_id=doc.id, document_version=doc.content_hash or "", source_type="patent", source_url=doc.source_url, location_type="claim" if locator.startswith("claim:") else "paragraph", claim_number=locator.split(":", 1)[1] if locator.startswith("claim:") else None, paragraph_range=locator if locator.startswith("paragraph:") else None, section="claims" if locator.startswith("claim:") else "description", quoted_text=quoted, normalized_meaning=feature.text, feature_ids=[feature.id], supports=[f"novelty:{doc.id}:{feature.id}"], confidence=0.9, verified=True, verification_method="source-fetch"))
        return state


class NoveltyEvaluationStep(_Step):
    def __init__(self) -> None:
        super().__init__("novelty_evaluation", CaseStatus.EVIDENCE_EXTRACTED, CaseStatus.NOVELTY_EVALUATED)

    async def run(self, state):
        state.novelty = evaluate_novelty(state.features, state.documents, state.evidence, state.priority_date) if state.evidence else NoveltyEvaluationResult(overall="uncertain")
        return state


class InventivenessEvaluationStep(_Step):
    def __init__(self, runner: SkillRunner) -> None:
        super().__init__("inventiveness_evaluation", CaseStatus.NOVELTY_EVALUATED, CaseStatus.INVENTIVENESS_EVALUATED)
        self.runner = runner

    async def run(self, state):
        await self.runner.run("patent-inventiveness", {"features": [{"id": f.id, "text": f.text} for f in state.features], "novelty": state.novelty.model_dump() if state.novelty else {}, "evidence": [item.model_dump() for item in state.evidence]})
        state.inventiveness = _build_inventiveness(state)
        return state


class CommercialValueStep(_Step):
    def __init__(self, runner: SkillRunner) -> None:
        super().__init__("commercial_value", CaseStatus.INVENTIVENESS_EVALUATED, CaseStatus.COMMERCIAL_VALUE_EVALUATED)
        self.runner = runner

    async def run(self, state):
        output = await self.runner.run("patent-commercial-value", {"idea": state.request.idea, "features": [{"id": f.id, "text": f.text} for f in state.features], "documents": [{"id": d.id, "title": d.title} for d in state.documents], "inventiveness": state.inventiveness.model_dump() if state.inventiveness else {}})
        confidence = float(output.get("confidence", 0.0))
        state.commercial_value = CommercialValueResult(enforceability={"claim_candidates": len(state.claims), "status": "preliminary"}, avoidability={"differentiating_features": len(state.features), "status": "preliminary"}, market_potential={"signals": output.get("market_signals", []), "risks": output.get("risks", [])}, scorecard=build_idea_scorecard(state), overall_confidence=max(0.0, min(1.0, confidence)))
        return state


class QualityStep(_Step):
    def __init__(self) -> None:
        super().__init__("quality_gate", CaseStatus.COMMERCIAL_VALUE_EVALUATED, CaseStatus.QUALITY_VALIDATED)

    async def run(self, state):
        state.quality = run_quality_gate(state)
        return state


class ReportStep(_Step):
    def __init__(self, cases_root: Path, runner: SkillRunner) -> None:
        super().__init__("report", CaseStatus.QUALITY_VALIDATED, CaseStatus.REPORT_RENDERED)
        self.cases_root, self.runner = cases_root, runner

    async def run(self, state):
        examiner = await self.runner.run("patent-examiner-opinion", {"novelty": state.novelty.model_dump() if state.novelty else {}, "inventiveness": state.inventiveness.model_dump() if state.inventiveness else {}, "quality": state.quality.model_dump() if state.quality else {}})
        state.invention["examiner_opinion"] = examiner.get("opinion", "")
        await self.runner.run("patent-report-renderer", {"case_id": state.case.id, "requested_outputs": state.request.requested_outputs, "state_revision": state.case.revision})
        self._write_reports(state)
        return state

    def _write_reports(self, state) -> None:
        directory = self.cases_root / state.case.id / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump(mode="json")
        report = _render_markdown(state)
        files = [("idea-review.md", "markdown", report), ("idea-review.json", "json", json.dumps(payload, ensure_ascii=False, indent=2))]
        state.artifacts = []
        for name, fmt, content in files:
            path = directory / name
            path.write_text(content, encoding="utf-8")
            state.artifacts.append(Artifact(name=name, format=fmt, path=str(path), content_hash=hashlib.sha256(content.encode()).hexdigest(), state_revision=state.case.revision))
        requested = set(state.request.requested_outputs)
        if "docx" in requested:
            path = directory / "idea-review.docx"
            render_docx(report, path)
            state.artifacts.append(Artifact(name=path.name, format="docx", path=str(path), content_hash=_file_hash(path), state_revision=state.case.revision))
        if "xlsx" in requested:
            path = directory / "idea-review.xlsx"
            render_xlsx(state, path)
            state.artifacts.append(Artifact(name=path.name, format="xlsx", path=str(path), content_hash=_file_hash(path), state_revision=state.case.revision))


class PartialReportStep(ReportStep):
    def __init__(self, cases_root: Path, runner: SkillRunner) -> None:
        super().__init__(cases_root, runner)
        self.name, self.allowed_from = "partial_report", frozenset({CaseStatus.PARTIAL})


class CompleteStep(_Step):
    def __init__(self) -> None:
        super().__init__("complete", CaseStatus.REPORT_RENDERED, CaseStatus.COMPLETED)

    async def run(self, state):
        return state


def build_default_steps(provider: SearchProvider, cases_root: Path, runner: SkillRunner | None = None) -> list[WorkflowStep]:
    runner = runner or default_skill_runner()
    return [IntakeStep(runner), FeatureExtractionStep(runner), SearchPlanningStep(runner), SearchStartedStep(), SearchExecutionStep(provider), DocumentRankingStep(), FullTextFetchStep(provider), EvidenceExtractionStep(runner), NoveltyEvaluationStep(), InventivenessEvaluationStep(runner), CommercialValueStep(runner), QualityStep(), ReportStep(cases_root, runner), PartialReportStep(cases_root, runner), CompleteStep()]


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _normalize_feature(value: Any) -> dict[str, str] | None:
    """Accept small, documented model-schema variations at the Skill boundary.

    The canonical persisted schema remains ``necessary|optional`` plus a
    limitation kind.  In particular, DeepSeek has returned ``essential`` /
    ``complementary`` and boolean ``limitation`` values in production; neither
    should silently turn a useful search plan into ``[\"zh\", \"en\"]``.
    """
    if not isinstance(value, dict):
        return None
    text = str(value.get("text", "")).strip()
    if not text:
        return None
    raw_kind = str(value.get("kind", "necessary")).strip().lower()
    kind = "optional" if raw_kind in {"optional", "complementary", "secondary", "可选", "补充"} else "necessary"
    raw_limitation = value.get("limitation")
    limitation = raw_limitation if raw_limitation in {"functional", "structural", "parameter", "step", "composition"} else _limitation_from_text(text)
    return {"text": text, "kind": kind, "limitation": limitation}


def _normalize_claims(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    claims: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, dict) and str(item.get("text", "")).strip():
            claims.append(item)
        elif isinstance(item, str) and item.strip():
            claims.append({"type": "independent" if index == 0 else "dependent", "text": item.strip()})
    return claims


def _normalize_query_terms(value: Any) -> list[str]:
    if isinstance(value, dict):
        values = [term for group in value.values() if isinstance(group, list) for term in group]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return list(dict.fromkeys(str(term).strip() for term in values if str(term).strip()))


def _limitation_from_text(text: str) -> str:
    if any(word in text for word in ("步骤", "方法", "执行", "输入", "输出", "生成", "融合", "分割")):
        return "step"
    if any(word in text for word in ("装置", "模块", "结构", "组件", "编码器", "解码器", "检测器")):
        return "structural"
    if any(word in text for word in ("比例", "温度", "阈值", "参数", "维度", "范围")):
        return "parameter"
    return "functional"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sections_from_content(content: str) -> list[dict[str, str]]:
    sections = []
    for index, line in enumerate((item.strip() for item in content.splitlines()), start=1):
        if not line:
            continue
        match = re.match(r"\[(claim:\d+|paragraph:\d+|abstract)\]\s*(.*)", line, flags=re.I)
        locator, text = (match.group(1), match.group(2)) if match else (f"paragraph:{index}", line)
        sections.append({"locator": locator.lower(), "text": text})
    return sections


def _find_feature_match(feature: str, sections: list[dict[str, str]]) -> tuple[str, str] | None:
    terms = _meaningful_terms(feature)
    for section in sections:
        text = str(section.get("text", ""))
        if feature.lower() in text.lower():
            # Preserve the source passage, not merely the feature paraphrase;
            # downstream D1/D2 analysis may need explicit combination language.
            return str(section["locator"]), text[: min(600, len(text))]
        hits = [term for term in terms if term.lower() in text.lower()]
        if terms and len(hits) / len(terms) >= 0.7:
            return str(section["locator"]), text[: min(600, len(text))]
    return None


def _meaningful_terms(text: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9]{3,}|[\u4e00-\u9fff]{2,}", text)
    return list(dict.fromkeys(terms))


def _build_inventiveness(state) -> InventiveStepResult:
    if not state.documents or not state.evidence:
        return InventiveStepResult(overall="uncertain")
    coverage: dict[str, set[str]] = {}
    for item in state.evidence:
        coverage.setdefault(item.document_id, set()).update(item.feature_ids)
    necessary = {feature.id for feature in state.features if feature.kind == "necessary"}
    candidates = sorted(coverage, key=lambda doc_id: len(coverage[doc_id] & necessary), reverse=True)[:state.budget.max_d1_routes]
    routes: list[InventiveStepRoute] = []
    for index, d1_id in enumerate(candidates, start=1):
        differences = sorted(necessary - coverage[d1_id])
        d2_ids = [doc_id for doc_id, items in coverage.items() if doc_id != d1_id and items & set(differences)]
        motivation = [item.id for item in state.evidence if item.document_id in d2_ids and any(token in item.quoted_text.lower() for token in ("combine", "combining", "结合", "组合", "替代"))]
        conclusion = "not-inventive" if differences and d2_ids and motivation else "uncertain"
        routes.append(InventiveStepRoute(id=f"ROUTE-{index:03d}", d1_document_id=d1_id, difference_feature_ids=differences, actual_technical_problem="依据区别特征待进一步核实", d2_document_ids=d2_ids[:state.budget.max_d2_per_feature], motivation_evidence_ids=motivation, conclusion=conclusion))
    overall = "not-inventive" if any(route.conclusion == "not-inventive" for route in routes) else "uncertain"
    return InventiveStepResult(routes=routes, strongest_route_id=routes[0].id if routes else None, overall=overall)


def _render_markdown(state) -> str:
    def rows(items):
        return "\n".join(items) or "- 无"
    novelty = state.novelty.overall if state.novelty else "uncertain"
    inventive = state.inventiveness.overall if state.inventiveness else "uncertain"
    scorecard = state.commercial_value.scorecard if state.commercial_value else None
    score_rows = [
        ("创新性", scorecard.innovation if scorecard else None, "第 5、6 章"),
        ("市场价值", scorecard.market_value if scorecard else None, "第 7 章"),
        ("侵权证据可获得性", scorecard.infringement_evidence_availability if scorecard else None, "第 7 章"),
        ("可规避性", scorecard.avoidability if scorecard else None, "第 7 章"),
    ]
    score_table = "\n".join(
        f"| {name} | {item.score:.1f} / 5 | {item.status} | {item.reason}（详见{chapter}） |"
        if item else f"| {name} | 0.0 / 5 | unavailable | 尚未完成评分 |"
        for name, item, chapter in score_rows
    )
    return f"""# 专利 IDEA 结构化评审报告

> 本报告基于可追溯检索和证据映射生成，不构成法律意见；“不确定”表示证据或检索范围不足，不能解释为肯定或否定结论。

## 评审速览（标准化 0–5 分）

> 1–5 分复用 PCT 评审量表；0 分仅表示当前缺少足以评分的证据，不表示该维度差。

| 维度 | 评分 | 状态 | 简要理由 |
| --- | --- | --- | --- |
{score_table}

## 1. 需求与技术方案

{state.request.idea}

## 2. 技术特征与拟定权利要求

{rows([f'- {item.id}（{item.kind}/{item.limitation}）：{item.text}' for item in state.features])}

## 3. 检索策略与执行记录

{rows([f'- {item.id} [{item.phase}]：{item.query_text}' for item in state.queries])}

## 4. 现有技术与全文证据

{rows([f'- {item.id} {item.publication_number or ""}：{item.title} — {item.source_url or "无链接"}' for item in state.documents])}

## 5. 新颖性分析

- 结论：{novelty}
- 优先权日：{state.priority_date or "未提供（不作日期有效性评审）"}
{rows([f'- {item.id} / {item.document_id} / {item.location_type}：{item.quoted_text}' for item in state.evidence])}

## 6. 创造性分析

- 结论：{inventive}
{rows([f'- {route.id}：D1={route.d1_document_id}；区别特征={", ".join(route.difference_feature_ids) or "无"}；D2={", ".join(route.d2_document_ids) or "无"}；结论={route.conclusion}' for route in (state.inventiveness.routes if state.inventiveness else [])])}

## 7. 商业价值与实施建议

- 置信度：{state.commercial_value.overall_confidence if state.commercial_value else 0.0}
- 风险：{(state.commercial_value.market_potential if state.commercial_value else {}).get("risks", [])}

## 8. 审查意见与质量门

{state.invention.get("examiner_opinion", "未生成")}

- 质量门：{'通过' if state.quality and state.quality.passed else '存在阻断或告警'}
{rows([f'- {item["code"]}：{item["message"]}' for item in (state.quality.errors if state.quality else [])])}
"""
