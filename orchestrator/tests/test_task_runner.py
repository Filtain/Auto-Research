import tempfile
import unittest
import csv
import json
from pathlib import Path

from orchestrator.src.agent_registry import AgentRegistry, AgentSpec
from orchestrator.src.orchestrator import TaskGraph, TaskNode
from orchestrator.src.task_runner import TaskRunResult, TaskRunner


class TaskRunnerTests(unittest.TestCase):
    def test_runs_ready_tasks_in_dependency_order(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="first",
                    agent="test_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                ),
                TaskNode(
                    task_id="T2",
                    task_name="second",
                    agent="test_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=["T1"],
                ),
            ]
        )
        calls = []

        def first(node, output_dir):
            calls.append(node.task_id)
            return TaskRunResult(status="completed", output={"ok": True})

        def second(node, output_dir):
            calls.append(node.task_id)
            return TaskRunResult(status="completed", output={"ok": True})

        registry = AgentRegistry(
            overrides={
                "first": AgentSpec("first", "test_agent", first, required=True),
                "second": AgentSpec("second", "test_agent", second, required=True),
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            TaskRunner(output_dir=tmpdir, registry=registry).run(graph)

        self.assertEqual(calls, ["T1", "T2"])
        self.assertTrue(all(node.status == "completed" for node in graph.nodes))

    def test_blocks_task_without_handler_and_downstream_dependency(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="missing_handler",
                    agent="missing_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                ),
                TaskNode(
                    task_id="T2",
                    task_name="downstream",
                    agent="test_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=["T1"],
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            TaskRunner(output_dir=tmpdir).run(graph)

        self.assertEqual(graph.nodes[0].status, "blocked")
        self.assertEqual(graph.nodes[1].status, "blocked")
        self.assertIn("No handler", graph.nodes[0].output["reason"])

    def test_skips_optional_task_without_handler(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="optional_missing",
                    agent="optional_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                    required=False,
                )
            ]
        )
        registry = AgentRegistry(
            overrides={
                "optional_missing": AgentSpec(
                    "optional_missing",
                    "optional_agent",
                    handler=None,
                    required=False,
                )
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            TaskRunner(output_dir=tmpdir, registry=registry).run(graph)

        self.assertEqual(graph.nodes[0].status, "skipped")

    def test_generate_search_queries_writes_artifact(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="generate_search_queries",
                    agent="planner_agent",
                    status="pending",
                    input={"topic": "BANF NeRF", "research_questions": ["What is BANF?"]},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((Path(tmpdir) / "search_queries.json").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertIn("search_queries_json", graph.nodes[0].output)

    def test_rank_sources_writes_ranked_outputs(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="rank_sources",
                    agent="paper_triage_agent",
                    status="pending",
                    input={"topic": "BANF NeRF"},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            papers_csv = Path(tmpdir) / "papers.csv"
            with papers_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "paper_id",
                        "title",
                        "authors",
                        "year",
                        "venue",
                        "doi",
                        "arxiv_id",
                        "url",
                        "abstract",
                        "citation_count",
                        "source",
                        "retrieved_at",
                        "query",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "paper_id": "p1",
                        "title": "BANF NeRF",
                        "authors": "A",
                        "year": "2026",
                        "venue": "arXiv",
                        "doi": "",
                        "arxiv_id": "1",
                        "url": "https://arxiv.org/abs/1",
                        "abstract": "BANF neural fields",
                        "citation_count": "",
                        "source": "arxiv",
                        "retrieved_at": "",
                        "query": "BANF",
                    }
                )

            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((Path(tmpdir) / "ranked_papers.csv").exists())
            self.assertTrue((Path(tmpdir) / "triage_report.md").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertEqual(graph.nodes[0].output["paper_count"], 1)

    def test_read_core_sources_writes_reading_outputs(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="read_core_sources",
                    agent="paper_reader_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ranked_csv = Path(tmpdir) / "ranked_papers.csv"
            with ranked_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rank",
                        "decision",
                        "score",
                        "paper_id",
                        "title",
                        "authors",
                        "year",
                        "venue",
                        "doi",
                        "arxiv_id",
                        "url",
                        "abstract",
                        "citation_count",
                        "source",
                        "retrieved_at",
                        "query",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "rank": "1",
                        "decision": "include",
                        "score": "0.9",
                        "paper_id": "p1",
                        "title": "BANF Neural Fields",
                        "authors": "A",
                        "year": "2026",
                        "venue": "arXiv",
                        "doi": "",
                        "arxiv_id": "1",
                        "url": "https://arxiv.org/abs/1",
                        "abstract": "We propose a neural field method.",
                        "citation_count": "",
                        "source": "arxiv",
                        "retrieved_at": "",
                        "query": "BANF",
                    }
                )

            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((Path(tmpdir) / "paper_readings.jsonl").exists())
            self.assertTrue((Path(tmpdir) / "paper_reading_report.md").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertEqual(graph.nodes[0].output["paper_count"], 1)

    def test_extract_evidence_writes_evidence_outputs(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="extract_evidence",
                    agent="evidence_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reading = {
                "paper_id": "p1",
                "paper_title": "BANF Neural Fields",
                "bibliographic_info": {"url": "https://arxiv.org/abs/1"},
                "full_text_available": False,
                "read_source": "abstract_metadata_only",
                "claims": [
                    {
                        "claim": "We propose a neural field method.",
                        "claim_type": "author_claim",
                        "evidence_text": "We propose a neural field method.",
                        "section": "abstract",
                        "page": None,
                        "confidence": "medium",
                    }
                ],
            }
            (output_dir / "paper_readings.jsonl").write_text(
                json.dumps(reading, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((output_dir / "evidence_store.jsonl").exists())
            self.assertTrue((output_dir / "source_map.json").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertEqual(graph.nodes[0].output["evidence_count"], 1)

    def test_synthesize_findings_writes_report_outputs(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="synthesize_findings",
                    agent="synthesis_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            evidence = {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "paper_title": "BANF Neural Fields",
                "claim": "We propose a neural field method.",
                "claim_type": "author_claim",
                "evidence_text": "We propose a neural field method.",
                "source_type": "paper",
                "source_location": {"section": "abstract", "page": None, "url": "https://arxiv.org/abs/1"},
                "support_level": "abstract_metadata_only",
                "full_text_available": False,
                "read_source": "abstract_metadata_only",
                "confidence": "medium",
            }
            source_map = {
                "papers": {
                    "p1": {
                        "paper_title": "BANF Neural Fields",
                        "bibliographic_info": {"url": "https://arxiv.org/abs/1"},
                        "full_text_available": False,
                        "read_source": "abstract_metadata_only",
                    }
                },
                "evidence_sources": {"p1:claim:1": {"paper_id": "p1"}},
            }
            (output_dir / "evidence_store.jsonl").write_text(
                json.dumps(evidence, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (output_dir / "source_map.json").write_text(
                json.dumps(source_map, ensure_ascii=False),
                encoding="utf-8",
            )

            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((output_dir / "report.md").exists())
            self.assertTrue((output_dir / "synthesis_summary.json").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertEqual(graph.nodes[0].output["evidence_count"], 1)

    def test_verify_claims_writes_verification_outputs(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="verify_claims",
                    agent="verifier_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            evidence = {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "paper_title": "BANF Neural Fields",
                "claim": "We propose a neural field method.",
                "claim_type": "author_claim",
                "evidence_text": "We propose a neural field method.",
                "source_type": "paper",
                "source_location": {
                    "section": "abstract",
                    "page": None,
                    "url": "https://arxiv.org/abs/1",
                    "read_source": "abstract_metadata_only",
                },
                "support_level": "abstract_metadata_only",
                "full_text_available": False,
                "read_source": "abstract_metadata_only",
                "confidence": "medium",
            }
            source_map = {
                "papers": {"p1": {"paper_title": "BANF Neural Fields"}},
                "evidence_sources": {"p1:claim:1": {"paper_id": "p1"}},
            }
            summary = {"paper_evidence": [{"paper_id": "p1", "evidence_ids": ["p1:claim:1"]}]}
            (output_dir / "evidence_store.jsonl").write_text(
                json.dumps(evidence, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (output_dir / "source_map.json").write_text(
                json.dumps(source_map, ensure_ascii=False),
                encoding="utf-8",
            )
            (output_dir / "synthesis_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False),
                encoding="utf-8",
            )
            (output_dir / "report.md").write_text(
                "- [p1:claim:1] We propose a neural field method.\n",
                encoding="utf-8",
            )

            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((output_dir / "verification_report.md").exists())
            self.assertTrue((output_dir / "verification_result.json").exists())
            self.assertTrue((output_dir / "claim_verification.jsonl").exists())
            self.assertTrue((output_dir / "unsupported_claims.jsonl").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertTrue(graph.nodes[0].output["verification_passed"])
        self.assertFalse(graph.nodes[0].output["publication_ready"])

    def test_final_qa_writes_final_gate_outputs(self) -> None:
        graph = TaskGraph(
            nodes=[
                TaskNode(
                    task_id="T1",
                    task_name="final_qa",
                    agent="final_qa_agent",
                    status="pending",
                    input={},
                    output=None,
                    depends_on=[],
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            required_files = [
                "report.md",
                "source_map.json",
                "evidence_store.jsonl",
                "synthesis_summary.json",
                "verification_report.md",
                "claim_verification.jsonl",
                "unsupported_claims.jsonl",
            ]
            for name in required_files:
                (output_dir / name).write_text("content\n", encoding="utf-8")
            (output_dir / "verification_result.json").write_text(
                json.dumps(
                    {
                        "verification_passed": True,
                        "publication_ready": False,
                        "checked_claim_count": 1,
                        "unsupported_claim_count": 0,
                        "missing_evidence_count": 0,
                        "abstract_only_warning_count": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            TaskRunner(output_dir=tmpdir).run(graph)
            self.assertTrue((output_dir / "final_qa_report.md").exists())
            self.assertTrue((output_dir / "final_qa_result.json").exists())

        self.assertEqual(graph.nodes[0].status, "completed")
        self.assertFalse(graph.nodes[0].output["export_allowed"])
        self.assertEqual(graph.nodes[0].output["warning_count"], 1)


if __name__ == "__main__":
    unittest.main()
