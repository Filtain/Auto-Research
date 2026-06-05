from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from benchmark.src.evaluator import ArtifactBenchmark
from comparison.src.comparator import MethodComparator
from evidence_db.src.evidence import EvidenceExtractor
from evaluation.src.evaluator import ResearchEvaluator
from experiment.src.planner import ExperimentPlanner
from experiment.src.runner import ExperimentRunner
from final_qa.src.final_gate import FinalQAGate
from idea_generation.src.generator import IdeaGenerator
from method_design.src.designer import MethodDesigner
from paper_triage.src.triage import PaperTriage
from paper_reader.src.reader import PaperReader
from planner.src.planner import Planner
from promotion.src.promoter import PromotionWriter
from rebuttal.src.rebuttal import RebuttalPlanner
from retriever.src.retriever import Retriever
from synthesis.src.synthesizer import FindingsSynthesizer
from verification.src.verifier import ClaimVerifier
from writer.src.writer import ResearchWriter


@dataclass
class AgentSpec:
    task_name: str
    agent_name: str
    handler: Callable[[Any, Path], Any] | None
    required: bool = True
    max_retries: int = 0
    description: str = ""


class AgentRegistry:
    """Registry that maps task names to runnable handlers and metadata."""

    def __init__(
        self,
        planner: Planner | None = None,
        retriever: Retriever | None = None,
        paper_triage: PaperTriage | None = None,
        paper_reader: PaperReader | None = None,
        evidence_extractor: EvidenceExtractor | None = None,
        findings_synthesizer: FindingsSynthesizer | None = None,
        claim_verifier: ClaimVerifier | None = None,
        final_qa_gate: FinalQAGate | None = None,
        method_comparator: MethodComparator | None = None,
        idea_generator: IdeaGenerator | None = None,
        method_designer: MethodDesigner | None = None,
        experiment_planner: ExperimentPlanner | None = None,
        experiment_runner: ExperimentRunner | None = None,
        research_evaluator: ResearchEvaluator | None = None,
        research_writer: ResearchWriter | None = None,
        promotion_writer: PromotionWriter | None = None,
        rebuttal_planner: RebuttalPlanner | None = None,
        artifact_benchmark: ArtifactBenchmark | None = None,
        overrides: dict[str, AgentSpec] | None = None,
    ) -> None:
        self.planner = planner or Planner()
        self.retriever = retriever or Retriever()
        self.paper_triage = paper_triage or PaperTriage()
        self.paper_reader = paper_reader or PaperReader()
        self.evidence_extractor = evidence_extractor or EvidenceExtractor()
        self.findings_synthesizer = findings_synthesizer or FindingsSynthesizer()
        self.claim_verifier = claim_verifier or ClaimVerifier()
        self.final_qa_gate = final_qa_gate or FinalQAGate()
        self.method_comparator = method_comparator or MethodComparator()
        self.idea_generator = idea_generator or IdeaGenerator()
        self.method_designer = method_designer or MethodDesigner()
        self.experiment_planner = experiment_planner or ExperimentPlanner()
        self.experiment_runner = experiment_runner or ExperimentRunner()
        self.research_evaluator = research_evaluator or ResearchEvaluator()
        self.research_writer = research_writer or ResearchWriter()
        self.promotion_writer = promotion_writer or PromotionWriter()
        self.rebuttal_planner = rebuttal_planner or RebuttalPlanner()
        self.artifact_benchmark = artifact_benchmark or ArtifactBenchmark()
        self.specs = self._default_specs()
        if overrides:
            self.specs.update(overrides)

    def get(self, task_name: str) -> AgentSpec | None:
        return self.specs.get(task_name)

    def agent_name_for(self, task_name: str) -> str:
        spec = self.get(task_name)
        if spec:
            return spec.agent_name
        return f"{task_name}_agent"

    def _default_specs(self) -> dict[str, AgentSpec]:
        return {
            "generate_search_queries": AgentSpec(
                task_name="generate_search_queries",
                agent_name="planner_agent",
                handler=self.handle_generate_search_queries,
                required=True,
                max_retries=0,
                description="Generate structured search queries and criteria.",
            ),
            "search_sources": AgentSpec(
                task_name="search_sources",
                agent_name="retriever_agent",
                handler=self.handle_search_sources,
                required=True,
                max_retries=1,
                description="Retrieve real paper metadata and write papers.csv.",
            ),
            "rank_sources": AgentSpec(
                task_name="rank_sources",
                agent_name="paper_triage_agent",
                handler=self.handle_rank_sources,
                required=True,
                description="Rank retrieved papers and write ranked_papers.csv.",
            ),
            "read_core_sources": AgentSpec(
                task_name="read_core_sources",
                agent_name="paper_reader_agent",
                handler=self.handle_read_core_sources,
                required=True,
                description="Read and structure core papers from ranked metadata.",
            ),
            "extract_evidence": AgentSpec(
                task_name="extract_evidence",
                agent_name="evidence_agent",
                handler=self.handle_extract_evidence,
                required=True,
                description="Create evidence records and source maps from paper readings.",
            ),
            "synthesize_findings": AgentSpec(
                task_name="synthesize_findings",
                agent_name="synthesis_agent",
                handler=self.handle_synthesize_findings,
                required=True,
                description="Synthesize findings from evidence records.",
            ),
            "compare_methods": AgentSpec(
                task_name="compare_methods",
                agent_name="comparison_agent",
                handler=self.handle_compare_methods,
                required=False,
                description="Build evidence-backed method and benchmark comparison matrices.",
            ),
            "generate_ideas": AgentSpec(
                task_name="generate_ideas",
                agent_name="idea_generation_agent",
                handler=self.handle_generate_ideas,
                required=False,
                description="Generate evidence-motivated idea candidates without novelty claims.",
            ),
            "design_method": AgentSpec(
                task_name="design_method",
                agent_name="method_design_agent",
                handler=self.handle_design_method,
                required=False,
                description="Create a proposed method spec and ablation plan from evidence-backed ideas.",
            ),
            "plan_experiments": AgentSpec(
                task_name="plan_experiments",
                agent_name="experiment_agent",
                handler=self.handle_plan_experiments,
                required=False,
                description="Create reproducibility and experiment planning artifacts.",
            ),
            "evaluate_results": AgentSpec(
                task_name="evaluate_results",
                agent_name="evaluation_agent",
                handler=self.handle_evaluate_results,
                required=False,
                description="Evaluate verification, QA, numeric checks, contradictions, and experiment coverage.",
            ),
            "run_experiments": AgentSpec(
                task_name="run_experiments",
                agent_name="experiment_agent",
                handler=self.handle_run_experiments,
                required=False,
                description="Run explicitly configured experiment commands and write execution logs.",
            ),
            "draft_paper": AgentSpec(
                task_name="draft_paper",
                agent_name="writer_agent",
                handler=self.handle_draft_paper,
                required=False,
                description="Compose final user-facing research report.",
            ),
            "draft_promotion": AgentSpec(
                task_name="draft_promotion",
                agent_name="promotion_agent",
                handler=self.handle_draft_promotion,
                required=False,
                description="Draft conservative dissemination artifacts and PPT outline.",
            ),
            "draft_rebuttal": AgentSpec(
                task_name="draft_rebuttal",
                agent_name="rebuttal_agent",
                handler=self.handle_draft_rebuttal,
                required=False,
                description="Draft response scaffolds from actual reviewer comments.",
            ),
            "verify_claims": AgentSpec(
                task_name="verify_claims",
                agent_name="verifier_agent",
                handler=self.handle_verify_claims,
                required=True,
                description="Verify claim traceability against evidence records.",
            ),
            "final_qa": AgentSpec(
                task_name="final_qa",
                agent_name="final_qa_agent",
                handler=self.handle_final_qa,
                required=True,
                description="Run final export QA gate.",
            ),
            "benchmark_evaluation": AgentSpec(
                task_name="benchmark_evaluation",
                agent_name="benchmark_agent",
                handler=self.handle_benchmark_evaluation,
                required=False,
                description="Evaluate artifact-level pipeline quality with optional ground truth.",
            ),
        }

    def handle_generate_search_queries(self, node: Any, output_dir: Path) -> dict[str, Any]:
        result = self.planner.generate_search_queries(task_input=node.input, output_dir=output_dir)
        return {
            "queries": [query.query for query in result.queries],
            "structured_queries": [
                {
                    "query": query.query,
                    "language": query.language,
                    "source_targets": query.source_targets,
                    "purpose": query.purpose,
                }
                for query in result.queries
            ],
            "inclusion_criteria": result.inclusion_criteria,
            "exclusion_criteria": result.exclusion_criteria,
            "search_queries_json": result.output_path,
        }

    def handle_search_sources(self, node: Any, output_dir: Path) -> dict[str, Any]:
        query = str(node.input.get("topic", "")).strip()
        max_results = int(node.input.get("min_sources", 8))
        source_targets = node.input.get("source_targets", ["arxiv"])
        if not isinstance(source_targets, list):
            source_targets = ["arxiv"]

        result = self.retriever.retrieve(
            query=query,
            output_dir=output_dir,
            max_results=max_results,
            sources=[str(source) for source in source_targets],
        )
        return {
            "paper_count": len(result.papers),
            "error_count": len(result.errors),
            "papers_csv": str(output_dir / "papers.csv"),
            "search_results_jsonl": str(output_dir / "search_results.jsonl"),
            "papers_raw_jsonl": str(output_dir / "papers_raw.jsonl"),
            "retrieval_errors_jsonl": str(output_dir / "retrieval_errors.jsonl"),
        }

    def handle_rank_sources(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("papers_csv", str(output_dir / "papers.csv"))
        result = self.paper_triage.rank_sources(task_input=task_input, output_dir=output_dir)
        return {
            "paper_count": result.paper_count,
            "included_count": result.included_count,
            "maybe_count": result.maybe_count,
            "excluded_count": result.excluded_count,
            "ranked_papers_csv": result.ranked_papers_csv,
            "triage_report_md": result.triage_report_md,
        }

    def handle_read_core_sources(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("ranked_papers_csv", str(output_dir / "ranked_papers.csv"))
        result = self.paper_reader.read_core_sources(task_input=task_input, output_dir=output_dir)
        return {
            "paper_count": result.paper_count,
            "abstract_only_count": result.abstract_only_count,
            "full_text_count": result.full_text_count,
            "claim_count": result.claim_count,
            "layout_block_count": result.layout_block_count,
            "paper_readings_jsonl": result.paper_readings_jsonl,
            "paper_reading_report_md": result.paper_reading_report_md,
            "paper_fulltext_chunks_jsonl": result.paper_fulltext_chunks_jsonl,
            "paper_layout_blocks_jsonl": result.paper_layout_blocks_jsonl,
            "paper_sections_jsonl": result.paper_sections_jsonl,
            "paper_tables_jsonl": result.paper_tables_jsonl,
            "paper_structured_tables_jsonl": result.paper_structured_tables_jsonl,
            "paper_structured_tables_csv": result.paper_structured_tables_csv,
            "paper_formulas_jsonl": result.paper_formulas_jsonl,
        }

    def handle_extract_evidence(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("paper_readings_jsonl", str(output_dir / "paper_readings.jsonl"))
        result = self.evidence_extractor.extract_evidence(task_input=task_input, output_dir=output_dir)
        return {
            "paper_count": result.paper_count,
            "evidence_count": result.evidence_count,
            "abstract_only_count": result.abstract_only_count,
            "evidence_store_jsonl": result.evidence_store_jsonl,
            "source_map_json": result.source_map_json,
        }

    def handle_synthesize_findings(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("evidence_store_jsonl", str(output_dir / "evidence_store.jsonl"))
        task_input.setdefault("source_map_json", str(output_dir / "source_map.json"))
        result = self.findings_synthesizer.synthesize_findings(task_input=task_input, output_dir=output_dir)
        return {
            "paper_count": result.paper_count,
            "evidence_count": result.evidence_count,
            "claim_type_count": result.claim_type_count,
            "abstract_only_evidence_count": result.abstract_only_evidence_count,
            "report_md": result.report_md,
            "synthesis_summary_json": result.synthesis_summary_json,
        }

    def handle_verify_claims(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("report_md", str(output_dir / "report.md"))
        task_input.setdefault("synthesis_summary_json", str(output_dir / "synthesis_summary.json"))
        task_input.setdefault("evidence_store_jsonl", str(output_dir / "evidence_store.jsonl"))
        task_input.setdefault("source_map_json", str(output_dir / "source_map.json"))
        task_input.setdefault("papers_raw_jsonl", str(output_dir / "papers_raw.jsonl"))
        task_input.setdefault("paper_tables_jsonl", str(output_dir / "paper_tables.jsonl"))
        result = self.claim_verifier.verify_claims(task_input=task_input, output_dir=output_dir)
        return {
            "verification_passed": result.verification_passed,
            "publication_ready": result.publication_ready,
            "checked_claim_count": result.checked_claim_count,
            "unsupported_claim_count": result.unsupported_claim_count,
            "missing_evidence_count": result.missing_evidence_count,
            "abstract_only_warning_count": result.abstract_only_warning_count,
            "verification_report_md": result.verification_report_md,
            "verification_result_json": result.verification_result_json,
            "claim_verification_jsonl": result.claim_verification_jsonl,
            "unsupported_claims_jsonl": result.unsupported_claims_jsonl,
            "citation_checks_jsonl": result.citation_checks_jsonl,
            "citation_authority_checks_jsonl": result.citation_authority_checks_jsonl,
            "citation_graph_checks_jsonl": result.citation_graph_checks_jsonl,
            "numeric_table_checks_jsonl": result.numeric_table_checks_jsonl,
            "contradiction_checks_jsonl": result.contradiction_checks_jsonl,
        }

    def handle_final_qa(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("verification_result_json", str(output_dir / "verification_result.json"))
        result = self.final_qa_gate.run_final_qa(task_input=task_input, output_dir=output_dir)
        return {
            "export_allowed": result.export_allowed,
            "publication_ready": result.publication_ready,
            "blocker_count": result.blocker_count,
            "warning_count": result.warning_count,
            "checked_artifact_count": result.checked_artifact_count,
            "final_qa_report_md": result.final_qa_report_md,
            "final_qa_result_json": result.final_qa_result_json,
        }

    def handle_compare_methods(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("evidence_store_jsonl", str(output_dir / "evidence_store.jsonl"))
        result = self.method_comparator.compare_methods(task_input=task_input, output_dir=output_dir)
        return {
            "paper_count": result.paper_count,
            "evidence_count": result.evidence_count,
            "literature_matrix_csv": result.literature_matrix_csv,
            "benchmark_matrix_csv": result.benchmark_matrix_csv,
            "comparison_report_md": result.comparison_report_md,
        }

    def handle_generate_ideas(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("synthesis_summary_json", str(output_dir / "synthesis_summary.json"))
        task_input.setdefault("evidence_store_jsonl", str(output_dir / "evidence_store.jsonl"))
        result = self.idea_generator.generate_ideas(task_input=task_input, output_dir=output_dir)
        return {
            "idea_count": result.idea_count,
            "evidence_reference_count": result.evidence_reference_count,
            "idea_candidates_md": result.idea_candidates_md,
            "idea_candidates_json": result.idea_candidates_json,
        }

    def handle_design_method(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("idea_candidates_json", str(output_dir / "idea_candidates.json"))
        task_input.setdefault("literature_matrix_csv", str(output_dir / "literature_matrix.csv"))
        result = self.method_designer.design_method(task_input=task_input, output_dir=output_dir)
        return {
            "component_count": result.component_count,
            "ablation_count": result.ablation_count,
            "method_spec_md": result.method_spec_md,
            "method_spec_json": result.method_spec_json,
            "ablation_plan_md": result.ablation_plan_md,
        }

    def handle_plan_experiments(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("literature_matrix_csv", str(output_dir / "literature_matrix.csv"))
        result = self.experiment_planner.plan_experiments(task_input=task_input, output_dir=output_dir)
        return {
            "item_count": result.item_count,
            "experiment_plan_md": result.experiment_plan_md,
            "reproduction_checklist_csv": result.reproduction_checklist_csv,
            "run_config_json": result.run_config_json,
        }

    def handle_run_experiments(self, node: Any, output_dir: Path) -> dict[str, Any]:
        task_input = dict(node.input)
        task_input.setdefault("run_config_json", str(output_dir / "run_config.json"))
        result = self.experiment_runner.run_experiments(task_input=task_input, output_dir=output_dir)
        return {
            "run_count": result.run_count,
            "completed_count": result.completed_count,
            "failed_count": result.failed_count,
            "dry_run_count": result.dry_run_count,
            "experiment_runs_jsonl": result.experiment_runs_jsonl,
            "results_table_csv": result.results_table_csv,
            "experiment_run_report_md": result.experiment_run_report_md,
        }

    def handle_evaluate_results(self, node: Any, output_dir: Path) -> dict[str, Any]:
        result = self.research_evaluator.evaluate_results(task_input=dict(node.input), output_dir=output_dir)
        return {
            "risk_count": result.risk_count,
            "missing_experiment_count": result.missing_experiment_count,
            "evaluation_report_md": result.evaluation_report_md,
            "missing_experiments_md": result.missing_experiments_md,
            "reviewer_risk_list_md": result.reviewer_risk_list_md,
        }

    def handle_draft_paper(self, node: Any, output_dir: Path) -> dict[str, Any]:
        result = self.research_writer.draft_paper(task_input=dict(node.input), output_dir=output_dir)
        return {
            "section_count": result.section_count,
            "final_report_md": result.final_report_md,
            "llm_call_log_jsonl": result.llm_call_log_jsonl,
        }

    def handle_draft_promotion(self, node: Any, output_dir: Path) -> dict[str, Any]:
        result = self.promotion_writer.draft_promotion(task_input=dict(node.input), output_dir=output_dir)
        return {
            "artifact_count": result.artifact_count,
            "promotion_brief_md": result.promotion_brief_md,
            "readme_draft_md": result.readme_draft_md,
            "project_page_copy_md": result.project_page_copy_md,
            "ppt_outline_md": result.ppt_outline_md,
        }

    def handle_draft_rebuttal(self, node: Any, output_dir: Path) -> dict[str, Any]:
        result = self.rebuttal_planner.draft_rebuttal(task_input=dict(node.input), output_dir=output_dir)
        return {
            "comment_count": result.comment_count,
            "checklist_count": result.checklist_count,
            "rebuttal_plan_md": result.rebuttal_plan_md,
            "response_to_reviewers_md": result.response_to_reviewers_md,
            "revision_checklist_md": result.revision_checklist_md,
        }

    def handle_benchmark_evaluation(self, node: Any, output_dir: Path) -> dict[str, Any]:
        result = self.artifact_benchmark.evaluate(task_input=dict(node.input), output_dir=output_dir)
        return {
            "overall_score": result.overall_score,
            "passed": result.passed,
            "layer_count": result.layer_count,
            "failure_count": result.failure_count,
            "benchmark_report_md": result.benchmark_report_md,
            "benchmark_scores_json": result.benchmark_scores_json,
            "benchmark_failures_jsonl": result.benchmark_failures_jsonl,
            "benchmark_summary_csv": result.benchmark_summary_csv,
        }
