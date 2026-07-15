"""Small, explicit boundary between the workflow and semantic Skills.

Each invocation receives a compact JSON state slice and returns JSON only.  A
model session never receives the accumulated raw search corpus or another
Skill's instruction text.  ``RuleBasedSkillRunner`` is deliberately useful in
offline/test deployments; production can select ``OpenCodeSkillRunner`` with
``IDEA_SKILL_RUNNER=opencode``.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class SkillRunner(ABC):
    @abstractmethod
    async def run(self, skill_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Run one named Skill and return a JSON object."""


class OpenCodeSkillRunner(SkillRunner):
    """Run a project Skill through OpenCode without sharing conversation state."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("IDEA_SKILL_MODEL", "deepseek/deepseek-v4-pro")

    async def run(self, skill_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        # Imported lazily so unit tests do not depend on app module import paths.
        try:
            from opencode_client import run_task
        except ImportError:
            from backend.opencode_client import run_task

        prompt = (
            f"请加载并严格执行项目 Skill `{skill_name}`。\n"
            "本次输入是受限 JSON 状态切片；不得假设看过其他上下文，不得编造来源。"
            "只输出一个合法 JSON 对象，不要 Markdown。\nINPUT:\n"
            + json.dumps(dict(payload), ensure_ascii=False)
        )
        output: list[str] = []
        async for event in run_task(prompt, model=self.model):
            if event.get("type") == "output":
                output.append(event.get("text", ""))
            if event.get("type") == "done" and event.get("result"):
                output = [event["result"]]
        return _parse_json("\n".join(output))


class RuleBasedSkillRunner(SkillRunner):
    """Offline semantic baseline with the same contracts as model-backed Skills.

    It keeps the workflow operable for CI and installations that have not yet
    configured a model.  It makes no legal conclusions and leaves provenance
    decisions to the evidence and domain layers.
    """

    async def run(self, skill_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if skill_name == "patent-idea-intake":
            idea = str(payload["idea"]).strip()
            return {"technical_field": _first_clause(idea), "problem": idea, "solution_summary": idea, "outputs": ["novelty", "inventiveness", "commercial", "examiner"]}
        if skill_name == "patent-feature-parser":
            idea = str(payload["idea"])
            parts = [part.strip() for part in re.split(r"[。；;\n]+", idea) if len(part.strip()) >= 3]
            return {
                "features": [
                    {"text": part, "kind": "necessary", "limitation": _limitation(part)}
                    for part in parts[:12]
                ] or [{"text": idea.strip(), "kind": "necessary", "limitation": "functional"}],
                "claims": [{"type": "independent", "text": idea.strip()}],
                "query_terms": _terms(idea),
            }
        if skill_name == "patent-search-planner":
            terms = payload.get("query_terms") or _terms(str(payload.get("idea", "")))
            joined = " ".join(terms[:8])
            return {"queries": [
                {"query_text": joined, "phase": "A", "intent": "核心方案精确检索"},
                {"query_text": " ".join(terms[:4]), "phase": "B", "intent": "关键特征扩展检索"},
            ], "strategy": "核心组合词与关键特征分批检索"}
        if skill_name == "patent-evidence-extractor":
            return {"matches": []}  # source-grounded extraction is performed by workflow code
        if skill_name == "patent-inventiveness":
            return {"routes": []}  # deterministic route builder remains evidence-bound
        if skill_name == "patent-commercial-value":
            return {"market_signals": [], "risks": ["未接入市场/竞争数据源"], "confidence": 0.2}
        if skill_name == "patent-examiner-opinion":
            return {"opinion": "证据与结论见结构化报告；应由专业人员作最终审查判断。"}
        if skill_name == "patent-report-renderer":
            return {"sections": ["需求与技术方案", "技术特征与拟定权利要求", "检索策略与执行记录", "现有技术与全文证据", "新颖性分析", "创造性分析", "商业价值与实施建议", "审查意见与质量门"]}
        raise ValueError(f"Unknown Skill: {skill_name}")


def default_skill_runner() -> SkillRunner:
    return OpenCodeSkillRunner() if os.environ.get("IDEA_SKILL_RUNNER", "").lower() == "opencode" else RuleBasedSkillRunner()


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    # Models sometimes preface an otherwise valid object with one explanatory
    # sentence or wrap it in a Markdown fence.  The workflow contract remains
    # JSON-only, but the transport boundary must extract that object rather
    # than turn a recoverable presentation deviation into a failed Case.
    candidates = [raw]
    candidates.extend(match.group(1).strip() for match in re.finditer(
        r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.I | re.S
    ))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    # Last fallback supports prose before a bare JSON object, while preserving
    # correct string escaping through JSONDecoder rather than regex parsing.
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("Skill did not return a valid JSON object")


def _first_clause(text: str) -> str:
    return re.split(r"[，,。；;\n]", text, maxsplit=1)[0].strip()


def _terms(text: str) -> list[str]:
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    latin = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", text.lower())
    return list(dict.fromkeys(cjk + latin))[:16]


def _limitation(text: str) -> str:
    if any(word in text for word in ("步骤", "方法", "执行", "计算")):
        return "step"
    if any(word in text for word in ("装置", "模块", "结构", "组件")):
        return "structural"
    if any(word in text for word in ("比例", "温度", "阈值", "参数")):
        return "parameter"
    return "functional"
