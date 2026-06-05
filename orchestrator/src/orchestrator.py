from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from retriever.src.retriever import Retriever
from orchestrator.src.agent_registry import AgentRegistry
from orchestrator.src.task_runner import TaskRunner


TASK_TYPE_KEYWORDS = {
    "literature_review": [
        "literature",
        "review",
        "survey",
        "paper",
        "论文",
        "文献",
        "调研",
        "综述",
        "找",
        "阅读",
    ],
    "method_analysis": [
        "method",
        "architecture",
        "structure",
        "方法",
        "结构",
        "网络",
        "模块",
        "创新点",
    ],
    "method_comparison": [
        "compare",
        "comparison",
        "vs",
        "versus",
        "difference",
        "区别",
        "对比",
        "比较",
    ],
    "idea_generation": ["idea", "gap", "novel", "创新", "想法", "研究空白"],
    "method_design": ["design", "improve", "改进", "设计", "方案"],
    "experiment_planning": [
        "experiment",
        "reproduce",
        "reproduction",
        "benchmark",
        "实验",
        "复现",
        "指标",
    ],
    "benchmark": ["benchmark", "基准", "评测基准", "可信度证明", "artifact quality"],
    "paper_writing": [
        "write",
        "draft",
        "introduction",
        "related work",
        "写",
        "论文",
        "草稿",
    ],
    "evaluation": ["evaluate", "评估", "评价", "reviewer risk"],
    "rebuttal": ["rebuttal", "reviewer", "response", "审稿", "回复", "修回"],
    "promotion": ["ppt", "slides", "poster", "blog", "展示", "答辩", "海报", "博客"],
    "ppt_generation": ["ppt", "slides", "大纲", "幻灯片"],
}

INTENT_RULES = {
    "literature_review": {
        "strong": ["literature review", "survey", "文献综述", "论文调研", "文献调研", "找.*论文", "读.*论文"],
        "weak": ["literature", "review", "paper", "论文", "文献", "调研", "综述", "找", "阅读"],
        "negative": [],
        "threshold": 1.0,
    },
    "method_analysis": {
        "strong": ["方法结构", "网络结构", "method architecture", "method structure", "创新点"],
        "weak": ["method", "architecture", "structure", "方法", "结构", "网络", "模块"],
        "negative": [],
        "threshold": 1.0,
    },
    "method_comparison": {
        "strong": [" vs ", "versus", "difference between", "区别", "对比", "比较"],
        "weak": ["compare", "comparison", "difference", "不同", "优缺点"],
        "negative": [],
        "threshold": 1.0,
    },
    "idea_generation": {
        "strong": ["generate.*idea", "research gap", "idea", "研究空白", "生成.*想法", "提出.*想法"],
        "weak": ["gap", "novel", "创新", "想法"],
        "negative": [],
        "threshold": 1.0,
    },
    "method_design": {
        "strong": ["method design", "设计.*方法", "改进.*方法", "设计.*方案"],
        "weak": ["design", "improve", "改进", "设计", "方案"],
        "negative": [],
        "threshold": 1.0,
    },
    "experiment_planning": {
        "strong": ["实验方案", "复现实验", "实验规划", "plan.*experiment", "reproduction plan"],
        "weak": ["experiment", "reproduce", "reproduction", "实验", "复现", "指标"],
        "negative": [],
        "threshold": 1.0,
    },
    "benchmark": {
        "strong": ["artifact benchmark", "dataset benchmark", "benchmark dataset", "可信度证明", "评测基准", "标准数据集评测", "大规模标准数据集"],
        "weak": ["benchmark", "基准", "评测"],
        "negative": ["benchmark matrix", "benchmark evidence"],
        "threshold": 1.0,
    },
    "paper_writing": {
        "strong": ["write.*paper", "draft.*paper", "写.*论文", "论文写作", "写.*introduction", "写.*related work", "撰写.*论文"],
        "weak": ["write", "draft", "introduction", "related work", "写", "草稿"],
        "negative": ["论文调研", "论文阅读", "找.*论文", "读.*论文", "paper review"],
        "threshold": 2.0,
    },
    "evaluation": {
        "strong": ["evaluate.*result", "结果评估", "评估结果", "reviewer risk", "风险评估"],
        "weak": ["evaluate", "评估", "评价"],
        "negative": ["benchmark evaluation"],
        "threshold": 1.0,
    },
    "rebuttal": {
        "strong": ["rebuttal", "response to reviewer", "审稿回复", "回复审稿", "修回"],
        "weak": ["reviewer", "response", "审稿", "回复"],
        "negative": [],
        "threshold": 1.0,
    },
    "promotion": {
        "strong": ["ppt", "slides", "poster", "project page", "readme", "答辩", "海报", "博客", "展示"],
        "weak": ["promotion", "推广"],
        "negative": [],
        "threshold": 1.0,
    },
    "ppt_generation": {
        "strong": ["ppt", "slides", "幻灯片", "ppt.*大纲"],
        "weak": ["大纲"],
        "negative": [],
        "threshold": 1.0,
    },
}

@dataclass
class UserRequest:
    user_query: str
    output_format: str = "report"
    language: str = "zh"
    depth: str = "medium"
    min_sources: int = 8
    execute: bool = False
    execute_retrieval: bool = False
    use_llm: bool = False
    llm_provider: str = "deterministic"
    llm_model: str = "none"
    run_experiments: bool = False
    experiment_dry_run: bool = True
    experiment_timeout_seconds: int = 300
    enable_authority_checks: bool = False
    run_benchmark: bool = False
    benchmark_spec: str = ""


@dataclass
class QualityRequirements:
    need_citations: bool = True
    need_source_trace: bool = True
    need_verification: bool = True
    allow_uncertain_claims: bool = False


@dataclass
class ResearchIntent:
    research_topic: str
    task_type: list[str]
    domain: str
    output_format: str
    depth: str
    need_citations: bool
    need_figures: bool


@dataclass
class ResearchPlan:
    project_id: str
    topic: str
    goal: str
    task_type: list[str]
    domain: str
    research_questions: list[str]
    expected_artifacts: list[str]
    quality_requirements: QualityRequirements


@dataclass
class TaskNode:
    task_id: str
    task_name: str
    agent: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    depends_on: list[str]
    retry_count: int = 0
    required: bool = True


@dataclass
class TaskGraph:
    nodes: list[TaskNode]


@dataclass
class RunEvent:
    time: str
    task_id: str
    agent: str
    status: str
    summary: str = ""
    error: str = ""


@dataclass
class RunLog:
    project_id: str
    logs: list[RunEvent] = field(default_factory=list)


@dataclass
class Artifact:
    name: str
    type: str
    created_by: str
    source_tasks: list[str]
    verified: bool
    path: str
    status: str = "planned"
    exists: bool = False
    created_at: str = ""


@dataclass
class ArtifactManifest:
    project_id: str
    artifacts: list[Artifact]


@dataclass
class FinalDecision:
    project_id: str
    export_allowed: bool
    reason: str
    quality_check: dict[str, bool]
    blocked_by: list[str]
    execution_summary: dict[str, int] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str, max_length: int = 48) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "_", text, flags=re.UNICODE).strip("_")
    return (text[:max_length].strip("_") or "auto_research")


class ResearchOrchestrator:
    """Deterministic MVP orchestrator for planning and control artifacts.

    This class intentionally does not retrieve papers or generate scientific
    conclusions. It creates the control plane needed by downstream agents.
    """

    def __init__(
        self,
        output_root: Path | str = "output",
        retriever: Retriever | None = None,
        registry: AgentRegistry | None = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.retriever = retriever or Retriever()
        self.registry = registry or AgentRegistry(retriever=self.retriever)

    def run(self, request: UserRequest) -> dict[str, Any]:
        intent = self.understand_query(request)
        plan = self.create_research_plan(intent, request)
        task_graph = self.build_task_graph(plan, request)
        project_dir = self.output_root / plan.project_id
        run_log = self.simulate_dispatch(plan.project_id, task_graph)
        if request.execute or request.execute_retrieval:
            self.execute_task_graph(task_graph=task_graph, run_log=run_log, project_dir=project_dir)
        manifest = self.create_artifact_manifest(plan, task_graph, project_dir)
        decision = self.final_check(plan, task_graph, manifest, request)
        project_dir = self.export_control_files(plan, task_graph, run_log, manifest, decision)
        manifest = self.create_artifact_manifest(plan, task_graph, project_dir)
        decision = self.final_check(plan, task_graph, manifest, request)
        self.write_orchestrator_report(project_dir, task_graph, manifest, decision)
        manifest = self.create_artifact_manifest(plan, task_graph, project_dir)
        decision = self.final_check(plan, task_graph, manifest, request)
        self._write_json(project_dir / "artifact_manifest.json", asdict(manifest))
        self._write_json(project_dir / "final_decision.json", asdict(decision))
        self.write_orchestrator_report(project_dir, task_graph, manifest, decision)

        return {
            "project_dir": str(project_dir),
            "research_plan": asdict(plan),
            "task_graph": asdict(task_graph),
            "run_log": asdict(run_log),
            "artifact_manifest": asdict(manifest),
            "final_decision": asdict(decision),
        }

    def understand_query(self, request: UserRequest) -> ResearchIntent:
        query = request.user_query.strip()
        query_lower = query.lower()
        task_types = self.classify_task_types(query_lower)
        if not task_types:
            task_types = ["literature_review"]
        if "literature_review" not in task_types:
            task_types.insert(0, "literature_review")

        output_format = self._infer_output_format(query_lower, request.output_format)
        if output_format == "ppt_outline" and "ppt_generation" not in task_types:
            task_types.append("ppt_generation")

        return ResearchIntent(
            research_topic=self._infer_topic(query),
            task_type=self._dedupe(task_types),
            domain=self._infer_domain(query_lower),
            output_format=output_format,
            depth=request.depth,
            need_citations=True,
            need_figures=output_format in {"ppt_outline", "slides", "report_with_figures"},
        )

    @classmethod
    def classify_task_types(cls, query_lower: str) -> list[str]:
        scores: dict[str, float] = {}
        for task_type, rule in INTENT_RULES.items():
            score = 0.0
            for pattern in rule.get("strong", []):
                if cls._intent_pattern_matches(str(pattern), query_lower):
                    score += 2.0
            for pattern in rule.get("weak", []):
                if cls._intent_pattern_matches(str(pattern), query_lower):
                    score += 1.0
            for pattern in rule.get("negative", []):
                if cls._intent_pattern_matches(str(pattern), query_lower):
                    score -= 2.0
            threshold = float(rule.get("threshold", 1.0))
            if score >= threshold:
                scores[task_type] = score

        cls._apply_intent_dependencies(scores, query_lower)
        ordered = [
            "literature_review",
            "method_analysis",
            "method_comparison",
            "idea_generation",
            "method_design",
            "experiment_planning",
            "benchmark",
            "paper_writing",
            "evaluation",
            "rebuttal",
            "promotion",
            "ppt_generation",
        ]
        return [task_type for task_type in ordered if task_type in scores]

    @staticmethod
    def _intent_pattern_matches(pattern: str, query_lower: str) -> bool:
        if ".*" in pattern or pattern.startswith("^") or pattern.endswith("$"):
            return re.search(pattern, query_lower) is not None
        return pattern.lower() in query_lower

    @staticmethod
    def _apply_intent_dependencies(scores: dict[str, float], query_lower: str) -> None:
        if "ppt_generation" in scores:
            scores["promotion"] = max(scores.get("promotion", 0.0), scores["ppt_generation"])
        if "method_comparison" in scores:
            scores["method_analysis"] = max(scores.get("method_analysis", 0.0), 1.0)
        if "method_design" in scores:
            scores["idea_generation"] = max(scores.get("idea_generation", 0.0), 0.0)
        if "benchmark" in scores and "experiment_planning" in scores:
            if "standard dataset" in query_lower or "标准数据集" in query_lower or "可信度证明" in query_lower:
                scores.pop("experiment_planning", None)

    def create_research_plan(self, intent: ResearchIntent, request: UserRequest) -> ResearchPlan:
        project_id = f"{slugify(intent.research_topic)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        questions = self._research_questions(intent)
        artifacts = self._expected_artifacts(intent)

        return ResearchPlan(
            project_id=project_id,
            topic=intent.research_topic,
            goal=request.user_query,
            task_type=intent.task_type,
            domain=intent.domain,
            research_questions=questions,
            expected_artifacts=artifacts,
            quality_requirements=QualityRequirements(),
        )

    def build_task_graph(self, plan: ResearchPlan, request: UserRequest) -> TaskGraph:
        tasks: list[tuple[str, dict[str, Any], list[str]]] = [
            (
                "generate_search_queries",
                {
                    "topic": plan.topic,
                    "research_questions": plan.research_questions,
                    "depth": request.depth,
                },
                [],
            ),
            (
                "search_sources",
                {
                    "topic": plan.topic,
                    "min_sources": request.min_sources,
                    "source_targets": ["arxiv"],
                },
                ["T1"],
            ),
            (
                "rank_sources",
                {
                    "topic": plan.topic,
                    "criteria": ["relevance", "recency", "impact", "full_text_available"],
                },
                ["T2"],
            ),
            (
                "read_core_sources",
                {
                    "schema": [
                        "problem",
                        "motivation",
                        "method",
                        "architecture",
                        "input_output",
                        "dataset",
                        "metrics",
                        "main_results",
                        "limitations",
                        "reproducibility",
                    ],
                },
                ["T3"],
            ),
            (
                "extract_evidence",
                {
                    "require_source_location": True,
                    "claim_types": ["fact", "author_claim", "comparison", "hypothesis"],
                },
                ["T4"],
            ),
            (
                "synthesize_findings",
                {
                    "outputs": ["research_trajectory", "gap_analysis", "reproducibility_route"],
                },
                ["T5"],
            ),
        ]

        if "method_comparison" in plan.task_type or "method_analysis" in plan.task_type:
            tasks.append(
                (
                    "compare_methods",
                    {"outputs": ["method_comparison", "experiment_comparison"]},
                    ["T5", "T6"],
                )
            )

        if "idea_generation" in plan.task_type:
            tasks.append(
                (
                    "generate_ideas",
                    {"source": "verified_gap_analysis", "max_ideas": 5},
                    [self._task_id_for(tasks, "synthesize_findings")],
                )
            )

        if "method_design" in plan.task_type:
            dependency = self._task_id_for(tasks, "generate_ideas") or self._task_id_for(
                tasks, "synthesize_findings"
            )
            tasks.append(("design_method", {"require_baseline_differences": True}, [dependency]))

        if "experiment_planning" in plan.task_type:
            dependency = (
                self._task_id_for(tasks, "design_method")
                or self._task_id_for(tasks, "compare_methods")
                or self._task_id_for(tasks, "synthesize_findings")
            )
            tasks.append(
                (
                    "plan_experiments",
                    {
                        "require_no_fabricated_results": True,
                        "mode": "plan_only",
                        "dry_run": request.experiment_dry_run,
                        "timeout_seconds": request.experiment_timeout_seconds,
                    },
                    [dependency],
                )
            )
            if request.run_experiments:
                tasks.append(
                    (
                        "run_experiments",
                        {
                            "dry_run": request.experiment_dry_run,
                            "timeout_seconds": request.experiment_timeout_seconds,
                        },
                        [self._task_id_for(tasks, "plan_experiments")],
                    )
                )

        if "evaluation" in plan.task_type:
            dependency = self._task_id_for(tasks, "plan_experiments") or self._task_id_for(
                tasks, "synthesize_findings"
            )
            tasks.append(("evaluate_results", {"mode": "evidence_strength"}, [dependency]))

        if "promotion" in plan.task_type or "ppt_generation" in plan.task_type:
            dependency = self._task_id_for(tasks, "synthesize_findings")
            tasks.append(("draft_promotion", {"format": "ppt_outline"}, [dependency]))

        if "rebuttal" in plan.task_type:
            dependency = self._task_id_for(tasks, "synthesize_findings")
            tasks.append(("draft_rebuttal", {"requires_reviewer_comments": True}, [dependency]))

        verification_deps = [
            task_id
            for task_id, task_name in self._task_ids_and_names(tasks)
            if task_name
            in {
                "synthesize_findings",
                "compare_methods",
                "generate_ideas",
                "design_method",
                "plan_experiments",
                "run_experiments",
                "evaluate_results",
                "draft_paper",
                "draft_promotion",
                "draft_rebuttal",
            }
        ]
        tasks.append(
            (
                "verify_claims",
                {
                    "require_citation_existence": True,
                    "require_claim_support": True,
                    "block_unsupported_factual_claims": True,
                    "enable_authority_checks": request.enable_authority_checks,
                },
                verification_deps,
            )
        )
        tasks.append(
            (
                "final_qa",
                {
                    "unsupported_claims_must_equal_zero": True,
                    "missing_citations_must_equal_zero": True,
                },
                [self._task_id_for(tasks, "verify_claims")],
            )
        )
        if request.run_benchmark or "benchmark" in plan.task_type:
            tasks.append(
                (
                    "benchmark_evaluation",
                    {
                        "benchmark_spec": request.benchmark_spec,
                        "pass_threshold": 0.75,
                    },
                    [self._task_id_for(tasks, "final_qa")],
                )
            )
        if "paper_writing" in plan.task_type:
            tasks.append(
                (
                    "draft_paper",
                    {
                        "format": "paper_section",
                        "use_llm": request.use_llm,
                        "llm_provider": request.llm_provider,
                        "llm_model": request.llm_model,
                    },
                    [self._task_id_for(tasks, "final_qa")],
                )
            )

        nodes = [
            TaskNode(
                task_id=f"T{index}",
                task_name=task_name,
                agent=self.registry.agent_name_for(task_name),
                status="pending",
                input=task_input,
                output=None,
                depends_on=depends_on,
                required=self.registry.get(task_name).required if self.registry.get(task_name) else True,
            )
            for index, (task_name, task_input, depends_on) in enumerate(tasks, start=1)
        ]
        return TaskGraph(nodes=nodes)

    def simulate_dispatch(self, project_id: str, task_graph: TaskGraph) -> RunLog:
        logs: list[RunEvent] = []
        for node in task_graph.nodes:
            logs.append(
                RunEvent(
                    time=utc_now(),
                    task_id=node.task_id,
                    agent=node.agent,
                    status="planned",
                    summary=f"Task {node.task_name} is ready for dispatch after dependencies: {node.depends_on}.",
                )
            )
        return RunLog(project_id=project_id, logs=logs)

    def execute_task_graph(self, task_graph: TaskGraph, run_log: RunLog, project_dir: Path) -> None:
        runner = TaskRunner(output_dir=project_dir, registry=self.registry)
        runner.run(task_graph=task_graph, log=lambda node, status, summary, error: self.append_run_log(
            run_log=run_log,
            node=node,
            status=status,
            summary=summary,
            error=error,
        ))

    @staticmethod
    def append_run_log(
        run_log: RunLog,
        node: TaskNode,
        status: str,
        summary: str = "",
        error: str = "",
    ) -> None:
        run_log.logs.append(
            RunEvent(
                time=utc_now(),
                task_id=node.task_id,
                agent=node.agent,
                status=status,
                summary=summary,
                error=error,
            )
        )

    def create_artifact_manifest(
        self, plan: ResearchPlan, task_graph: TaskGraph, project_dir: Path | None = None
    ) -> ArtifactManifest:
        base_dir = project_dir or (self.output_root / plan.project_id)
        artifacts = [
            self._build_artifact(
                name=name,
                type=self._artifact_type(name),
                created_by=self._artifact_creator(name),
                source_tasks=self._source_tasks_for_artifact(name, task_graph),
                path=str(base_dir / name),
            )
            for name in plan.expected_artifacts
        ]
        artifacts.extend(
            [
                self._build_artifact(
                    name="research_plan.json",
                    type="json",
                    created_by="orchestrator_agent",
                    source_tasks=[],
                    path=str(base_dir / "research_plan.json"),
                ),
                self._build_artifact(
                    name="task_graph.json",
                    type="json",
                    created_by="orchestrator_agent",
                    source_tasks=[],
                    path=str(base_dir / "task_graph.json"),
                ),
                self._build_artifact(
                    name="orchestrator_report.md",
                    type="markdown",
                    created_by="orchestrator_agent",
                    source_tasks=[],
                    path=str(base_dir / "orchestrator_report.md"),
                ),
                self._build_artifact(
                    name="search_queries.json",
                    type="json",
                    created_by="planner_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "generate_search_queries"
                    ],
                    path=str(base_dir / "search_queries.json"),
                ),
                self._build_artifact(
                    name="search_results.jsonl",
                    type="jsonl",
                    created_by="retriever_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "search_sources"
                    ],
                    path=str(base_dir / "search_results.jsonl"),
                ),
                self._build_artifact(
                    name="papers_raw.jsonl",
                    type="jsonl",
                    created_by="retriever_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "search_sources"
                    ],
                    path=str(base_dir / "papers_raw.jsonl"),
                ),
                self._build_artifact(
                    name="ranked_papers.csv",
                    type="csv",
                    created_by="paper_triage_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "rank_sources"
                    ],
                    path=str(base_dir / "ranked_papers.csv"),
                ),
                self._build_artifact(
                    name="triage_report.md",
                    type="markdown",
                    created_by="paper_triage_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "rank_sources"
                    ],
                    path=str(base_dir / "triage_report.md"),
                ),
                self._build_artifact(
                    name="paper_readings.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_readings.jsonl"),
                ),
                self._build_artifact(
                    name="paper_reading_report.md",
                    type="markdown",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_reading_report.md"),
                ),
                self._build_artifact(
                    name="paper_fulltext_chunks.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_fulltext_chunks.jsonl"),
                ),
                self._build_artifact(
                    name="paper_layout_blocks.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_layout_blocks.jsonl"),
                ),
                self._build_artifact(
                    name="paper_sections.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_sections.jsonl"),
                ),
                self._build_artifact(
                    name="paper_tables.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_tables.jsonl"),
                ),
                self._build_artifact(
                    name="paper_structured_tables.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_structured_tables.jsonl"),
                ),
                self._build_artifact(
                    name="paper_structured_tables.csv",
                    type="csv",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_structured_tables.csv"),
                ),
                self._build_artifact(
                    name="paper_formulas.jsonl",
                    type="jsonl",
                    created_by="paper_reader_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "read_core_sources"
                    ],
                    path=str(base_dir / "paper_formulas.jsonl"),
                ),
                self._build_artifact(
                    name="evidence_store.jsonl",
                    type="jsonl",
                    created_by="evidence_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "extract_evidence"
                    ],
                    path=str(base_dir / "evidence_store.jsonl"),
                ),
                self._build_artifact(
                    name="synthesis_summary.json",
                    type="json",
                    created_by="synthesis_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "synthesize_findings"
                    ],
                    path=str(base_dir / "synthesis_summary.json"),
                ),
                self._build_artifact(
                    name="verification_report.md",
                    type="markdown",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "verification_report.md"),
                ),
                self._build_artifact(
                    name="verification_result.json",
                    type="json",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "verification_result.json"),
                ),
                self._build_artifact(
                    name="claim_verification.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "claim_verification.jsonl"),
                ),
                self._build_artifact(
                    name="unsupported_claims.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "unsupported_claims.jsonl"),
                ),
                self._build_artifact(
                    name="citation_checks.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "citation_checks.jsonl"),
                ),
                self._build_artifact(
                    name="citation_authority_checks.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "citation_authority_checks.jsonl"),
                ),
                self._build_artifact(
                    name="citation_graph_checks.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "citation_graph_checks.jsonl"),
                ),
                self._build_artifact(
                    name="numeric_table_checks.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "numeric_table_checks.jsonl"),
                ),
                self._build_artifact(
                    name="contradiction_checks.jsonl",
                    type="jsonl",
                    created_by="verifier_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "verify_claims"
                    ],
                    path=str(base_dir / "contradiction_checks.jsonl"),
                ),
                self._build_artifact(
                    name="benchmark_matrix.csv",
                    type="csv",
                    created_by="comparison_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "compare_methods"
                    ],
                    path=str(base_dir / "benchmark_matrix.csv"),
                ),
                self._build_artifact(
                    name="comparison_report.md",
                    type="markdown",
                    created_by="comparison_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "compare_methods"
                    ],
                    path=str(base_dir / "comparison_report.md"),
                ),
                self._build_artifact(
                    name="reproduction_checklist.csv",
                    type="csv",
                    created_by="experiment_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "plan_experiments"
                    ],
                    path=str(base_dir / "reproduction_checklist.csv"),
                ),
                self._build_artifact(
                    name="run_config.json",
                    type="json",
                    created_by="experiment_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "plan_experiments"
                    ],
                    path=str(base_dir / "run_config.json"),
                ),
                self._build_artifact(
                    name="experiment_runs.jsonl",
                    type="jsonl",
                    created_by="experiment_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "run_experiments"
                    ],
                    path=str(base_dir / "experiment_runs.jsonl"),
                ),
                self._build_artifact(
                    name="results_table.csv",
                    type="csv",
                    created_by="experiment_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "run_experiments"
                    ],
                    path=str(base_dir / "results_table.csv"),
                ),
                self._build_artifact(
                    name="experiment_run_report.md",
                    type="markdown",
                    created_by="experiment_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "run_experiments"
                    ],
                    path=str(base_dir / "experiment_run_report.md"),
                ),
                self._build_artifact(
                    name="final_report.md",
                    type="markdown",
                    created_by="writer_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "draft_paper"
                    ],
                    path=str(base_dir / "final_report.md"),
                ),
                self._build_artifact(
                    name="llm_calls.jsonl",
                    type="jsonl",
                    created_by="writer_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "draft_paper"
                    ],
                    path=str(base_dir / "llm_calls.jsonl"),
                ),
                self._build_artifact(
                    name="final_qa_report.md",
                    type="markdown",
                    created_by="final_qa_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "final_qa"
                    ],
                    path=str(base_dir / "final_qa_report.md"),
                ),
                self._build_artifact(
                    name="final_qa_result.json",
                    type="json",
                    created_by="final_qa_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "final_qa"
                    ],
                    path=str(base_dir / "final_qa_result.json"),
                ),
                self._build_artifact(
                    name="benchmark_report.md",
                    type="markdown",
                    created_by="benchmark_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "benchmark_evaluation"
                    ],
                    path=str(base_dir / "benchmark_report.md"),
                ),
                self._build_artifact(
                    name="benchmark_scores.json",
                    type="json",
                    created_by="benchmark_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "benchmark_evaluation"
                    ],
                    path=str(base_dir / "benchmark_scores.json"),
                ),
                self._build_artifact(
                    name="benchmark_failures.jsonl",
                    type="jsonl",
                    created_by="benchmark_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "benchmark_evaluation"
                    ],
                    path=str(base_dir / "benchmark_failures.jsonl"),
                ),
                self._build_artifact(
                    name="benchmark_summary.csv",
                    type="csv",
                    created_by="benchmark_agent",
                    source_tasks=[
                        node.task_id for node in task_graph.nodes if node.task_name == "benchmark_evaluation"
                    ],
                    path=str(base_dir / "benchmark_summary.csv"),
                ),
            ]
        )
        return ArtifactManifest(project_id=plan.project_id, artifacts=artifacts)

    def _build_artifact(
        self,
        name: str,
        type: str,
        created_by: str,
        source_tasks: list[str],
        path: str,
    ) -> Artifact:
        exists = Path(path).exists()
        status = "created" if exists else "planned"
        return Artifact(
            name=name,
            type=type,
            created_by=created_by,
            source_tasks=source_tasks,
            verified=exists,
            path=path,
            status=status,
            exists=exists,
            created_at=utc_now() if exists else "",
        )

    def final_check(
        self,
        plan: ResearchPlan,
        task_graph: TaskGraph,
        manifest: ArtifactManifest,
        request: UserRequest,
    ) -> FinalDecision:
        task_names = {node.task_name for node in task_graph.nodes}
        summary = self.execution_summary(task_graph)
        missing_required_artifacts = [
            artifact.name
            for artifact in manifest.artifacts
            if artifact.name in {"research_plan.json", "task_graph.json"}
            and not artifact.exists
        ]
        quality_check = {
            "has_clear_research_question": bool(plan.research_questions),
            "has_sufficient_source_target": request.min_sources > 0,
            "has_citations_for_key_claims": plan.quality_requirements.need_citations,
            "has_source_trace": plan.quality_requirements.need_source_trace,
            "has_verification_task": "verify_claims" in task_names,
            "has_final_qa_task": "final_qa" in task_names,
            "has_final_output": bool(manifest.artifacts),
            "blocks_uncertain_factual_claims": not plan.quality_requirements.allow_uncertain_claims,
            "required_control_artifacts_exist": not missing_required_artifacts,
        }
        if request.execute or request.execute_retrieval:
            quality_check["has_no_failed_tasks"] = not any(
                node.status == "failed" and node.required for node in task_graph.nodes
            )
            quality_check["has_no_blocked_required_tasks"] = not any(
                node.status == "blocked" and node.required for node in task_graph.nodes
            )
            quality_check["retrieval_completed_if_executed"] = any(
                node.task_name == "search_sources" and node.status == "completed"
                for node in task_graph.nodes
            )
            final_qa_node = next((node for node in task_graph.nodes if node.task_name == "final_qa"), None)
            final_qa_output = final_qa_node.output if final_qa_node and isinstance(final_qa_node.output, dict) else {}
            quality_check["final_qa_completed_if_executed"] = bool(
                final_qa_node and final_qa_node.status == "completed"
            )
            quality_check["final_qa_export_allowed"] = bool(final_qa_output.get("export_allowed"))
        blocked_by = [key for key, passed in quality_check.items() if not passed]
        return FinalDecision(
            project_id=plan.project_id,
            export_allowed=not blocked_by,
            reason="Control artifacts are ready." if not blocked_by else "Quality gate failed.",
            quality_check=quality_check,
            blocked_by=blocked_by,
            execution_summary=summary,
        )

    @staticmethod
    def execution_summary(task_graph: TaskGraph) -> dict[str, int]:
        summary = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "skipped": 0,
            "required_failed": 0,
            "required_blocked": 0,
        }
        for node in task_graph.nodes:
            summary[node.status] = summary.get(node.status, 0) + 1
            if node.required and node.status == "failed":
                summary["required_failed"] += 1
            if node.required and node.status == "blocked":
                summary["required_blocked"] += 1
        return summary

    def export_control_files(
        self,
        plan: ResearchPlan,
        task_graph: TaskGraph,
        run_log: RunLog,
        manifest: ArtifactManifest,
        decision: FinalDecision,
    ) -> Path:
        project_dir = self.output_root / plan.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(project_dir / "research_plan.json", asdict(plan))
        self._write_json(project_dir / "task_graph.json", asdict(task_graph))
        self._write_json(project_dir / "run_log.json", asdict(run_log))
        self._write_json(project_dir / "artifact_manifest.json", asdict(manifest))
        self._write_json(project_dir / "final_decision.json", asdict(decision))
        return project_dir

    @staticmethod
    def write_orchestrator_report(
        project_dir: Path,
        task_graph: TaskGraph,
        manifest: ArtifactManifest,
        decision: FinalDecision,
    ) -> None:
        lines = [
            "# Orchestrator Report",
            "",
            "## Final Decision",
            "",
            f"- export_allowed: {str(decision.export_allowed).lower()}",
            f"- reason: {decision.reason}",
            f"- blocked_by: {', '.join(decision.blocked_by) if decision.blocked_by else 'none'}",
            "",
            "## Execution Summary",
            "",
        ]
        for key, value in decision.execution_summary.items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Tasks", ""])
        for node in task_graph.nodes:
            required = "required" if node.required else "optional"
            lines.append(f"- {node.task_id} `{node.task_name}`: {node.status} ({required})")
            if node.output and node.output.get("reason"):
                lines.append(f"  reason: {node.output['reason']}")
        lines.extend(["", "## Artifacts", ""])
        for artifact in manifest.artifacts:
            lines.append(f"- `{artifact.name}`: {artifact.status} exists={str(artifact.exists).lower()}")
        lines.extend(
            [
                "",
                "## Next Actions",
                "",
                "- Implement handlers for blocked required tasks before treating the research workflow as complete.",
                "- Keep unsupported claims out of final artifacts until verification exists.",
            ]
        )
        (project_dir / "orchestrator_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    @staticmethod
    def _infer_output_format(query_lower: str, default: str) -> str:
        if "ppt" in query_lower or "slides" in query_lower or "大纲" in query_lower:
            return "ppt_outline"
        if "csv" in query_lower or "表格" in query_lower:
            return "matrix"
        return default

    @staticmethod
    def _infer_domain(query_lower: str) -> str:
        if any(term in query_lower for term in ["nerf", "banf", "gaussian", "3d", "vision", "图像"]):
            return "computer_vision"
        if any(term in query_lower for term in ["cuda", "pytorch", "gpu"]):
            return "deep_learning_systems"
        if any(term in query_lower for term in ["protein", "biology", "cell", "gene"]):
            return "life_science"
        return "general_research"

    @staticmethod
    def _infer_topic(query: str) -> str:
        cleaned = query.strip()
        cleaned = re.sub(r"^(帮我|请|我想|我要|帮忙)", "", cleaned)
        cleaned = re.sub(r"(并|，|,|。).*", "", cleaned)
        cleaned = cleaned.strip() or query.strip()
        return cleaned[:120]

    @staticmethod
    def _research_questions(intent: ResearchIntent) -> list[str]:
        topic = intent.research_topic
        questions = [
            f"What is the precise research scope of {topic}?",
            f"What core sources are needed to understand {topic}?",
            f"What are the main methods, assumptions, and limitations related to {topic}?",
        ]
        if "method_comparison" in intent.task_type:
            questions.append(f"How do the key methods related to {topic} differ?")
        if "experiment_planning" in intent.task_type:
            questions.append(f"How can the methods related to {topic} be reproduced or evaluated?")
        if "idea_generation" in intent.task_type:
            questions.append(f"What verified research gaps can motivate new ideas for {topic}?")
        return questions

    @staticmethod
    def _expected_artifacts(intent: ResearchIntent) -> list[str]:
        artifacts = ["report.md", "papers.csv", "source_map.json"]
        if "method_comparison" in intent.task_type or "method_analysis" in intent.task_type:
            artifacts.append("literature_matrix.csv")
        if "experiment_planning" in intent.task_type:
            artifacts.append("experiment_plan.md")
        if "idea_generation" in intent.task_type:
            artifacts.append("idea_candidates.md")
            artifacts.append("idea_candidates.json")
        if "method_design" in intent.task_type:
            artifacts.extend(["method_spec.md", "method_spec.json", "ablation_plan.md"])
        if "evaluation" in intent.task_type:
            artifacts.extend(["evaluation_report.md", "missing_experiments.md", "reviewer_risk_list.md"])
        if "benchmark" in intent.task_type:
            artifacts.extend(
                [
                    "benchmark_report.md",
                    "benchmark_scores.json",
                    "benchmark_failures.jsonl",
                    "benchmark_summary.csv",
                ]
            )
        if "rebuttal" in intent.task_type:
            artifacts.extend(["rebuttal_plan.md", "response_to_reviewers.md", "revision_checklist.md"])
        if "promotion" in intent.task_type:
            artifacts.extend(["promotion_brief.md", "readme_draft.md", "project_page_copy.md"])
        if intent.output_format == "ppt_outline" or "ppt_generation" in intent.task_type:
            artifacts.append("ppt_outline.md")
        return ResearchOrchestrator._dedupe(artifacts)

    @staticmethod
    def _task_ids_and_names(tasks: list[tuple[str, dict[str, Any], list[str]]]) -> list[tuple[str, str]]:
        return [(f"T{index}", task_name) for index, (task_name, _, _) in enumerate(tasks, start=1)]

    @staticmethod
    def _task_id_for(tasks: list[tuple[str, dict[str, Any], list[str]]], task_name: str) -> str:
        for index, (existing_task_name, _, _) in enumerate(tasks, start=1):
            if existing_task_name == task_name:
                return f"T{index}"
        return ""

    @staticmethod
    def _artifact_type(name: str) -> str:
        suffix = Path(name).suffix.lower()
        if suffix == ".md":
            return "markdown"
        if suffix == ".csv":
            return "csv"
        if suffix == ".json":
            return "json"
        if suffix == ".jsonl":
            return "jsonl"
        if suffix == ".bib":
            return "bibtex"
        return "file"

    @staticmethod
    def _artifact_creator(name: str) -> str:
        if name in {"final_qa_report.md", "final_qa_result.json"}:
            return "final_qa_agent"
        if name in {
            "benchmark_report.md",
            "benchmark_scores.json",
            "benchmark_failures.jsonl",
            "benchmark_summary.csv",
        }:
            return "benchmark_agent"
        if name in {
            "verification_report.md",
            "verification_result.json",
            "claim_verification.jsonl",
            "unsupported_claims.jsonl",
            "citation_checks.jsonl",
            "citation_authority_checks.jsonl",
            "citation_graph_checks.jsonl",
            "numeric_table_checks.jsonl",
            "contradiction_checks.jsonl",
        }:
            return "verifier_agent"
        if name in {
            "paper_fulltext_chunks.jsonl",
            "paper_layout_blocks.jsonl",
            "paper_sections.jsonl",
            "paper_tables.jsonl",
            "paper_structured_tables.jsonl",
            "paper_structured_tables.csv",
            "paper_formulas.jsonl",
        }:
            return "paper_reader_agent"
        if name in {"benchmark_matrix.csv", "comparison_report.md"}:
            return "comparison_agent"
        if name in {
            "reproduction_checklist.csv",
            "run_config.json",
            "experiment_runs.jsonl",
            "results_table.csv",
            "experiment_run_report.md",
        }:
            return "experiment_agent"
        if name in {"final_report.md", "llm_calls.jsonl"}:
            return "writer_agent"
        if name in {"idea_candidates.md", "idea_candidates.json"}:
            return "idea_generation_agent"
        if name in {"method_spec.md", "method_spec.json", "ablation_plan.md"}:
            return "method_design_agent"
        if name in {"evaluation_report.md", "missing_experiments.md", "reviewer_risk_list.md"}:
            return "evaluation_agent"
        if name in {"rebuttal_plan.md", "response_to_reviewers.md", "revision_checklist.md"}:
            return "rebuttal_agent"
        if name in {"promotion_brief.md", "readme_draft.md", "project_page_copy.md", "ppt_outline.md"}:
            return "promotion_agent"
        if name in {"report.md", "synthesis_summary.json"}:
            return "synthesis_agent"
        if name in {"evidence_store.jsonl", "source_map.json"}:
            return "evidence_agent"
        if name in {"paper_readings.jsonl", "paper_reading_report.md"}:
            return "paper_reader_agent"
        if name in {"ranked_papers.csv", "triage_report.md"}:
            return "paper_triage_agent"
        if name in {"papers.csv", "papers_raw.jsonl", "search_results.jsonl"}:
            return "retriever_agent"
        if name == "search_queries.json":
            return "planner_agent"
        if "matrix" in name or "comparison" in name:
            return "comparison_agent"
        if "experiment" in name or "reproduction" in name:
            return "experiment_agent"
        if "idea" in name:
            return "idea_generation_agent"
        if "source_map" in name:
            return "evidence_agent"
        return "writer_agent"

    @staticmethod
    def _source_tasks_for_artifact(name: str, task_graph: TaskGraph) -> list[str]:
        if name == "search_queries.json":
            wanted = {"generate_search_queries"}
        elif name in {
            "benchmark_report.md",
            "benchmark_scores.json",
            "benchmark_failures.jsonl",
            "benchmark_summary.csv",
        }:
            wanted = {"benchmark_evaluation"}
        elif name in {"final_qa_report.md", "final_qa_result.json"}:
            wanted = {"final_qa"}
        elif name in {
            "verification_report.md",
            "verification_result.json",
            "claim_verification.jsonl",
            "unsupported_claims.jsonl",
            "citation_checks.jsonl",
            "citation_authority_checks.jsonl",
            "citation_graph_checks.jsonl",
            "numeric_table_checks.jsonl",
            "contradiction_checks.jsonl",
        }:
            wanted = {"verify_claims"}
        elif name in {"benchmark_matrix.csv", "comparison_report.md"}:
            wanted = {"compare_methods"}
        elif name in {"reproduction_checklist.csv", "run_config.json"}:
            wanted = {"plan_experiments"}
        elif name in {"experiment_runs.jsonl", "results_table.csv", "experiment_run_report.md"}:
            wanted = {"run_experiments"}
        elif name in {"final_report.md", "llm_calls.jsonl"}:
            wanted = {"draft_paper"}
        elif name in {"idea_candidates.md", "idea_candidates.json"}:
            wanted = {"generate_ideas"}
        elif name in {"method_spec.md", "method_spec.json", "ablation_plan.md"}:
            wanted = {"design_method"}
        elif name in {"evaluation_report.md", "missing_experiments.md", "reviewer_risk_list.md"}:
            wanted = {"evaluate_results"}
        elif name in {"rebuttal_plan.md", "response_to_reviewers.md", "revision_checklist.md"}:
            wanted = {"draft_rebuttal"}
        elif name in {"promotion_brief.md", "readme_draft.md", "project_page_copy.md", "ppt_outline.md"}:
            wanted = {"draft_promotion"}
        elif name in {"report.md", "synthesis_summary.json"}:
            wanted = {"synthesize_findings"}
        elif name in {"evidence_store.jsonl", "source_map.json"}:
            wanted = {"extract_evidence"}
        elif name in {
            "paper_readings.jsonl",
            "paper_reading_report.md",
            "paper_fulltext_chunks.jsonl",
            "paper_layout_blocks.jsonl",
            "paper_sections.jsonl",
            "paper_tables.jsonl",
            "paper_structured_tables.jsonl",
            "paper_structured_tables.csv",
            "paper_formulas.jsonl",
        }:
            wanted = {"read_core_sources"}
        elif name in {"ranked_papers.csv", "triage_report.md"}:
            wanted = {"rank_sources"}
        elif name in {"papers.csv", "papers_raw.jsonl", "search_results.jsonl"}:
            wanted = {"search_sources"}
        elif "source_map" in name:
            wanted = {"extract_evidence"}
        elif "matrix" in name or "comparison" in name:
            wanted = {"compare_methods"}
        elif "experiment" in name or "reproduction" in name:
            wanted = {"plan_experiments"}
        elif "idea" in name:
            wanted = {"generate_ideas"}
        else:
            wanted = {"synthesize_findings", "verify_claims"}
        return [node.task_id for node in task_graph.nodes if node.task_name in wanted]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Auto Research orchestrator control files.")
    parser.add_argument("query", help="User research request.")
    parser.add_argument("--output-format", default="report", help="Requested output format.")
    parser.add_argument("--language", default="zh", help="Output language.")
    parser.add_argument("--depth", default="medium", choices=["light", "medium", "detailed"])
    parser.add_argument("--min-sources", type=int, default=8)
    parser.add_argument("--output-root", default="output")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable optional LLM-assisted writing. Disabled by default.",
    )
    parser.add_argument(
        "--llm-provider",
        default="deterministic",
        help="LLM provider for optional writing, for example: deterministic or openai.",
    )
    parser.add_argument(
        "--llm-model",
        default="none",
        help="LLM model for optional writing, for example: gpt-4.1-mini.",
    )
    parser.add_argument(
        "--run-experiments",
        action="store_true",
        help="Add and execute the experiment runner node when an experiment-planning task is detected.",
    )
    parser.add_argument(
        "--execute-experiment-commands",
        action="store_true",
        help="Actually run configured experiment commands. By default experiment runner is dry-run only.",
    )
    parser.add_argument(
        "--experiment-timeout-seconds",
        type=int,
        default=300,
        help="Timeout for each configured experiment command.",
    )
    parser.add_argument(
        "--enable-authority-checks",
        action="store_true",
        help="Enable external citation authority checks through DOI/arXiv/OpenAlex/Semantic Scholar providers.",
    )
    parser.add_argument(
        "--run-benchmark",
        action="store_true",
        help="Run artifact-level benchmark evaluation after Final QA.",
    )
    parser.add_argument(
        "--benchmark-spec",
        default="",
        help="Optional JSON ground-truth spec for artifact-level benchmark evaluation.",
    )
    parser.add_argument(
        "--execute-retrieval",
        action="store_true",
        help="Compatibility alias for --execute. Executes runnable DAG tasks.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the task graph with registered handlers.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    request = UserRequest(
        user_query=args.query,
        output_format=args.output_format,
        language=args.language,
        depth=args.depth,
        min_sources=args.min_sources,
        execute=args.execute,
        execute_retrieval=args.execute_retrieval,
        use_llm=args.use_llm,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        run_experiments=args.run_experiments,
        experiment_dry_run=not args.execute_experiment_commands,
        experiment_timeout_seconds=args.experiment_timeout_seconds,
        enable_authority_checks=args.enable_authority_checks,
        run_benchmark=args.run_benchmark,
        benchmark_spec=args.benchmark_spec,
    )
    result = ResearchOrchestrator(output_root=args.output_root).run(request)
    print(json.dumps({"project_dir": result["project_dir"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
