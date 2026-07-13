"""Golden baseline tests.

按 design doc Section 12.1 Golden Cases 要求:
离线 fixture 重复运行结果一致。
"""

from .fixtures import (
    golden_single_doc_full_coverage,
    golden_multi_doc_partial_coverage,
    golden_d1_d2_with_motivation,
    golden_d2_no_motivation,
    golden_late_publication_date,
    golden_evidence_no_location,
    golden_vague_idea,
    run_all_golden_scenarios,
)
from backend.patent_analysis.services.novelty import evaluate_novelty
from backend.patent_analysis.services.quality import run_quality_gate


class TestGoldenSingleDocFullCoverage:
    def test_single_doc_full_coverage_is_not_novel(self):
        state = golden_single_doc_full_coverage()
        result = evaluate_novelty(
            state.features, state.documents, state.evidence, state.priority_date
        )
        assert result.overall == "not-novel"

    def test_single_doc_quality_passes(self):
        state = golden_single_doc_full_coverage()
        qr = run_quality_gate(state)
        assert qr.passed is True


class TestGoldenMultiDocPartialCoverage:
    def test_multi_doc_partial_is_novel(self):
        state = golden_multi_doc_partial_coverage()
        result = evaluate_novelty(
            state.features, state.documents, state.evidence, state.priority_date
        )
        assert result.overall == "novel"


class TestGoldenD1D2WithMotivation:
    def test_d1_d2_with_motivation(self):
        state = golden_d1_d2_with_motivation()
        assert state.inventiveness is not None
        assert state.inventiveness.overall == "not-inventive"
        assert state.inventiveness.routes[0].conclusion == "not-inventive"
        assert len(state.inventiveness.routes[0].motivation_evidence_ids) > 0


class TestGoldenD2NoMotivation:
    def test_d2_no_motivation_is_inventive(self):
        state = golden_d2_no_motivation()
        assert state.inventiveness is not None
        assert state.inventiveness.overall == "inventive"
        assert state.inventiveness.routes[0].motivation_evidence_ids == []


class TestGoldenLatePublicationDate:
    def test_late_publication_is_novel(self):
        state = golden_late_publication_date()
        result = evaluate_novelty(
            state.features, state.documents, state.evidence, state.priority_date
        )
        assert result.overall == "novel"

    def test_late_publication_quality_has_error(self):
        state = golden_late_publication_date()
        qr = run_quality_gate(state)
        codes = {e["code"] for e in qr.errors}
        assert "DATE_POST_PRIORITY" in codes


class TestGoldenEvidenceNoLocation:
    def test_evidence_no_location_quality_fails(self):
        state = golden_evidence_no_location()
        qr = run_quality_gate(state)
        assert qr.passed is False
        codes = {e["code"] for e in qr.errors}
        assert "EVIDENCE_NO_LOCATION" in codes


class TestGoldenVagueIdea:
    def test_vague_idea_is_novel(self):
        state = golden_vague_idea()
        result = evaluate_novelty(
            state.features, state.documents, state.evidence, state.priority_date
        )
        assert result.overall == "novel"


class TestGoldenRunner:
    def test_all_scenarios_produce_results(self):
        results = run_all_golden_scenarios()
        assert len(results) == 7
        assert results["single-doc-full-coverage"]["novelty"] == "not-novel"
        assert results["multi-doc-partial"]["novelty"] == "novel"
        assert results["late-publication-date"]["novelty"] == "novel"
        assert results["late-publication-date"]["quality_passed"] is False
        assert results["evidence-no-location"]["quality_passed"] is False
        assert results["vague-idea"]["novelty"] == "novel"
