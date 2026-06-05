import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.src.orchestrator import ResearchOrchestrator, UserRequest, parse_args
from retriever.src.retriever import PaperRecord, RetrievalResult


class FakeRetriever:
    def retrieve(self, query, output_dir, max_results=20, sources=None):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        paper = PaperRecord(
            paper_id="arxiv:1234_5678",
            title="A Retrieved Paper",
            authors=["Ada Lovelace"],
            year="2026",
            venue="arXiv",
            doi="",
            arxiv_id="1234.5678",
            url="https://arxiv.org/abs/1234.5678",
            abstract="We propose a neural field method for reconstruction.",
            citation_count="",
            source="arxiv",
            retrieved_at="2026-05-25T00:00:00+00:00",
            query=query,
        )
        from retriever.src.retriever import Retriever

        result = RetrievalResult(papers=[paper], errors=[])
        Retriever.write_outputs(result=result, output_dir=output_path)
        return result


class EmptyRetriever:
    def retrieve(self, query, output_dir, max_results=20, sources=None):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        from retriever.src.retriever import Retriever

        result = RetrievalResult(papers=[], errors=[])
        Retriever.write_outputs(result=result, output_dir=output_path)
        return result


class ResearchOrchestratorTests(unittest.TestCase):
    def test_generates_control_files_for_literature_and_ppt_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ResearchOrchestrator(output_root=tmpdir)
            result = orchestrator.run(
                UserRequest(
                    user_query="帮我调研 3D Gaussian Splatting 和 NeRF 的区别，并生成一个 PPT 大纲",
                    output_format="ppt",
                    depth="medium",
                )
            )

            project_dir = Path(result["project_dir"])
            self.assertTrue((project_dir / "research_plan.json").exists())
            self.assertTrue((project_dir / "task_graph.json").exists())
            self.assertTrue((project_dir / "run_log.json").exists())
            self.assertTrue((project_dir / "artifact_manifest.json").exists())
            self.assertTrue((project_dir / "final_decision.json").exists())
            self.assertTrue((project_dir / "orchestrator_report.md").exists())

            plan = json.loads((project_dir / "research_plan.json").read_text(encoding="utf-8"))
            self.assertIn("literature_review", plan["task_type"])
            self.assertIn("method_comparison", plan["task_type"])
            self.assertIn("ppt_generation", plan["task_type"])
            self.assertIn("ppt_outline.md", plan["expected_artifacts"])

    def test_task_graph_contains_verification_and_final_qa(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(user_query="帮我做一个关于 BANF 的完整论文调研，并给出复现建议")
            )
            task_graph = result["task_graph"]
            task_names = {node["task_name"] for node in task_graph["nodes"]}

            self.assertIn("verify_claims", task_names)
            self.assertIn("final_qa", task_names)

            final_qa = next(node for node in task_graph["nodes"] if node["task_name"] == "final_qa")
            verifier = next(node for node in task_graph["nodes"] if node["task_name"] == "verify_claims")
            self.assertEqual(final_qa["depends_on"], [verifier["task_id"]])

    def test_intent_detection_does_not_treat_paper_research_as_paper_writing(self) -> None:
        intent = ResearchOrchestrator().understand_query(
            UserRequest(user_query="帮我做一个关于 BANF 的完整论文调研，并给出复现建议")
        )

        self.assertIn("literature_review", intent.task_type)
        self.assertIn("experiment_planning", intent.task_type)
        self.assertNotIn("paper_writing", intent.task_type)

    def test_intent_detection_keeps_explicit_review_writing(self) -> None:
        intent = ResearchOrchestrator().understand_query(
            UserRequest(user_query="帮我写 BANF 论文综述")
        )

        self.assertIn("literature_review", intent.task_type)
        self.assertIn("paper_writing", intent.task_type)

    def test_intent_detection_handles_dataset_benchmark_without_experiment_planning(self) -> None:
        intent = ResearchOrchestrator().understand_query(
            UserRequest(user_query="把 Benchmark 升级成大规模标准数据集评测框架")
        )

        self.assertIn("benchmark", intent.task_type)
        self.assertNotIn("experiment_planning", intent.task_type)

    def test_intent_detection_derives_promotion_from_ppt_outline(self) -> None:
        intent = ResearchOrchestrator().understand_query(
            UserRequest(user_query="准备 BANF 答辩 PPT 大纲")
        )

        self.assertIn("promotion", intent.task_type)
        self.assertIn("ppt_generation", intent.task_type)
        self.assertEqual(intent.output_format, "ppt_outline")

    def test_llm_cli_options_flow_to_writer_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(
                    user_query="帮我写 BANF 论文综述",
                    use_llm=True,
                    llm_provider="openai",
                    llm_model="gpt-4.1-mini",
                )
            )
            draft_task = next(node for node in result["task_graph"]["nodes"] if node["task_name"] == "draft_paper")

            self.assertTrue(draft_task["input"]["use_llm"])
            self.assertEqual(draft_task["input"]["llm_provider"], "openai")
            self.assertEqual(draft_task["input"]["llm_model"], "gpt-4.1-mini")

    def test_writer_llm_is_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(user_query="帮我写 BANF 论文综述")
            )
            draft_task = next(node for node in result["task_graph"]["nodes"] if node["task_name"] == "draft_paper")

            self.assertFalse(draft_task["input"]["use_llm"])

    def test_parse_args_accepts_llm_options(self) -> None:
        args = parse_args(
            [
                "帮我写 BANF 论文综述",
                "--use-llm",
                "--llm-provider",
                "openai",
                "--llm-model",
                "gpt-4.1-mini",
            ]
        )

        self.assertTrue(args.use_llm)
        self.assertEqual(args.llm_provider, "openai")
        self.assertEqual(args.llm_model, "gpt-4.1-mini")

    def test_run_experiment_options_add_runner_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(
                    user_query="帮我规划 BANF 复现实验",
                    run_experiments=True,
                    experiment_dry_run=True,
                    experiment_timeout_seconds=12,
                )
            )
            task_names = [node["task_name"] for node in result["task_graph"]["nodes"]]
            run_task = next(node for node in result["task_graph"]["nodes"] if node["task_name"] == "run_experiments")

            self.assertIn("plan_experiments", task_names)
            self.assertIn("run_experiments", task_names)
            self.assertTrue(run_task["input"]["dry_run"])
            self.assertEqual(run_task["input"]["timeout_seconds"], 12)

    def test_parse_args_accepts_experiment_runner_options(self) -> None:
        args = parse_args(
            [
                "帮我规划 BANF 复现实验",
                "--run-experiments",
                "--execute-experiment-commands",
                "--experiment-timeout-seconds",
                "12",
            ]
        )

        self.assertTrue(args.run_experiments)
        self.assertTrue(args.execute_experiment_commands)
        self.assertEqual(args.experiment_timeout_seconds, 12)

    def test_authority_check_option_flows_to_verifier_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(
                    user_query="帮我找 BANF 相关论文",
                    enable_authority_checks=True,
                )
            )
            verifier_task = next(node for node in result["task_graph"]["nodes"] if node["task_name"] == "verify_claims")

        self.assertTrue(verifier_task["input"]["enable_authority_checks"])

    def test_later_research_stage_tasks_and_artifacts_are_planned(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(
                    user_query="帮我生成 BANF idea，设计改进方法，评估结果，准备 rebuttal 和 PPT 展示",
                    output_format="ppt",
                )
            )
            task_names = {node["task_name"] for node in result["task_graph"]["nodes"]}
            artifact_names = {artifact["name"] for artifact in result["artifact_manifest"]["artifacts"]}

            self.assertIn("generate_ideas", task_names)
            self.assertIn("design_method", task_names)
            self.assertIn("evaluate_results", task_names)
            self.assertIn("draft_rebuttal", task_names)
            self.assertIn("draft_promotion", task_names)
            self.assertIn("idea_candidates.json", artifact_names)
            self.assertIn("method_spec.json", artifact_names)
            self.assertIn("evaluation_report.md", artifact_names)
            self.assertIn("response_to_reviewers.md", artifact_names)
            self.assertIn("promotion_brief.md", artifact_names)
            self.assertIn("ppt_outline.md", artifact_names)

    def test_execute_later_research_stage_handlers_create_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir, retriever=FakeRetriever()).run(
                UserRequest(
                    user_query="帮我生成 BANF idea，设计改进方法，规划实验，评估结果，准备 rebuttal 和 PPT 展示",
                    output_format="ppt",
                    execute=True,
                )
            )
            project_dir = Path(result["project_dir"])
            task_names = {
                node["task_name"]: node
                for node in result["task_graph"]["nodes"]
            }

            self.assertEqual(task_names["generate_ideas"]["status"], "completed")
            self.assertEqual(task_names["design_method"]["status"], "completed")
            self.assertEqual(task_names["plan_experiments"]["status"], "completed")
            self.assertEqual(task_names["evaluate_results"]["status"], "completed")
            self.assertEqual(task_names["draft_rebuttal"]["status"], "completed")
            self.assertEqual(task_names["draft_promotion"]["status"], "completed")
            self.assertTrue((project_dir / "idea_candidates.json").exists())
            self.assertTrue((project_dir / "method_spec.json").exists())
            self.assertTrue((project_dir / "ablation_plan.md").exists())
            self.assertTrue((project_dir / "evaluation_report.md").exists())
            self.assertTrue((project_dir / "response_to_reviewers.md").exists())
            self.assertTrue((project_dir / "promotion_brief.md").exists())
            self.assertTrue((project_dir / "ppt_outline.md").exists())

    def test_parse_args_accepts_authority_check_option(self) -> None:
        args = parse_args(["帮我找 BANF 相关论文", "--enable-authority-checks"])

        self.assertTrue(args.enable_authority_checks)

    def test_benchmark_options_add_artifact_benchmark_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "benchmark_spec.json"
            spec_path.write_text(json.dumps({"expected_export_allowed": False}), encoding="utf-8")
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(
                    user_query="帮我找 BANF 相关论文",
                    run_benchmark=True,
                    benchmark_spec=str(spec_path),
                )
            )
            task_names = {node["task_name"] for node in result["task_graph"]["nodes"]}
            benchmark_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "benchmark_evaluation"
            )
            artifact_names = {artifact["name"] for artifact in result["artifact_manifest"]["artifacts"]}

            self.assertIn("benchmark_evaluation", task_names)
            self.assertEqual(benchmark_task["input"]["benchmark_spec"], str(spec_path))
            self.assertIn("benchmark_report.md", artifact_names)
            self.assertIn("benchmark_scores.json", artifact_names)

    def test_parse_args_accepts_benchmark_options(self) -> None:
        args = parse_args(["帮我找 BANF 相关论文", "--run-benchmark", "--benchmark-spec", "spec.json"])

        self.assertTrue(args.run_benchmark)
        self.assertEqual(args.benchmark_spec, "spec.json")

    def test_quality_gate_blocks_invalid_min_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir).run(
                UserRequest(user_query="帮我找 BANF 相关论文", min_sources=0)
            )
            decision = result["final_decision"]

            self.assertFalse(decision["export_allowed"])
            self.assertIn("has_sufficient_source_target", decision["blocked_by"])

    def test_execute_retrieval_writes_papers_csv_and_updates_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir, retriever=FakeRetriever()).run(
                UserRequest(user_query="帮我找 BANF 相关论文", execute_retrieval=True)
            )

            project_dir = Path(result["project_dir"])
            self.assertTrue((project_dir / "papers.csv").exists())
            self.assertTrue((project_dir / "search_queries.json").exists())
            search_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "search_sources"
            )
            self.assertEqual(search_task["status"], "completed")
            self.assertEqual(search_task["output"]["paper_count"], 1)
            rank_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "rank_sources"
            )
            self.assertEqual(rank_task["status"], "completed")
            self.assertEqual(rank_task["output"]["paper_count"], 1)
            read_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "read_core_sources"
            )
            self.assertEqual(read_task["status"], "completed")
            self.assertEqual(read_task["output"]["paper_count"], 1)
            evidence_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "extract_evidence"
            )
            self.assertEqual(evidence_task["status"], "completed")
            self.assertEqual(evidence_task["output"]["evidence_count"], 1)
            synthesis_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "synthesize_findings"
            )
            self.assertEqual(synthesis_task["status"], "completed")
            self.assertEqual(synthesis_task["output"]["evidence_count"], 1)
            verifier_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "verify_claims"
            )
            self.assertEqual(verifier_task["status"], "completed")
            self.assertTrue(verifier_task["output"]["verification_passed"])
            self.assertFalse(verifier_task["output"]["publication_ready"])
            final_qa_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "final_qa"
            )
            self.assertEqual(final_qa_task["status"], "completed")
            self.assertFalse(final_qa_task["output"]["export_allowed"])
            self.assertFalse(result["final_decision"]["export_allowed"])
            self.assertIn("final_qa_export_allowed", result["final_decision"]["blocked_by"])
            self.assertEqual(result["final_decision"]["execution_summary"]["completed"], 8)
            self.assertTrue((project_dir / "ranked_papers.csv").exists())
            self.assertTrue((project_dir / "triage_report.md").exists())
            self.assertTrue((project_dir / "paper_readings.jsonl").exists())
            self.assertTrue((project_dir / "paper_reading_report.md").exists())
            self.assertTrue((project_dir / "evidence_store.jsonl").exists())
            self.assertTrue((project_dir / "source_map.json").exists())
            self.assertTrue((project_dir / "report.md").exists())
            self.assertTrue((project_dir / "synthesis_summary.json").exists())
            self.assertTrue((project_dir / "verification_report.md").exists())
            self.assertTrue((project_dir / "verification_result.json").exists())
            self.assertTrue((project_dir / "claim_verification.jsonl").exists())
            self.assertTrue((project_dir / "unsupported_claims.jsonl").exists())
            self.assertTrue((project_dir / "final_qa_report.md").exists())
            self.assertTrue((project_dir / "final_qa_result.json").exists())
            manifest = result["artifact_manifest"]
            search_queries_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "search_queries.json"
            )
            self.assertTrue(search_queries_artifact["exists"])
            self.assertEqual(search_queries_artifact["status"], "created")
            report_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "orchestrator_report.md"
            )
            self.assertTrue(report_artifact["exists"])
            ranked_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "ranked_papers.csv"
            )
            self.assertTrue(ranked_artifact["exists"])
            readings_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "paper_readings.jsonl"
            )
            self.assertTrue(readings_artifact["exists"])
            evidence_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "evidence_store.jsonl"
            )
            self.assertTrue(evidence_artifact["exists"])
            source_map_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "source_map.json"
            )
            self.assertTrue(source_map_artifact["exists"])
            report_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "report.md"
            )
            self.assertTrue(report_artifact["exists"])
            verification_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "verification_report.md"
            )
            self.assertTrue(verification_artifact["exists"])
            final_qa_artifact = next(
                artifact for artifact in manifest["artifacts"] if artifact["name"] == "final_qa_report.md"
            )
            self.assertTrue(final_qa_artifact["exists"])

    def test_execute_retrieval_blocks_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResearchOrchestrator(output_root=tmpdir, retriever=EmptyRetriever()).run(
                UserRequest(user_query="帮我找 BANF 相关论文", execute_retrieval=True)
            )

            search_task = next(
                node for node in result["task_graph"]["nodes"] if node["task_name"] == "search_sources"
            )
            self.assertEqual(search_task["status"], "blocked")
            self.assertEqual(search_task["output"]["paper_count"], 0)


if __name__ == "__main__":
    unittest.main()
