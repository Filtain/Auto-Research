import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.src.evaluator import ArtifactBenchmark


class ArtifactBenchmarkTests(unittest.TestCase):
    def test_scores_artifact_layers_with_ground_truth_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            self.write_fixture(output)
            (output / "benchmark_spec.json").write_text(
                json.dumps(
                    {
                        "expected_papers": [{"title": "A Retrieved Paper"}],
                        "triage_top_k": 1,
                        "expected_sections": ["method"],
                        "expected_evidence_ids": ["arxiv:1234_5678:claim:1"],
                        "required_synthesis_topics": ["neural field"],
                        "expected_unsupported_claim_count": 0,
                        "expected_export_allowed": False,
                        "expected_safe_export": False,
                    }
                ),
                encoding="utf-8",
            )

            result = ArtifactBenchmark().evaluate({}, output)
            payload = json.loads((output / "benchmark_scores.json").read_text(encoding="utf-8"))

            self.assertTrue((output / "benchmark_report.md").exists())
            self.assertTrue((output / "benchmark_failures.jsonl").exists())
            self.assertTrue((output / "benchmark_summary.csv").exists())
            self.assertEqual(result.layer_count, 8)
            self.assertTrue(payload["has_ground_truth_spec"])
            self.assertGreaterEqual(result.overall_score, 0.8)

    def test_missing_expected_paper_creates_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            self.write_fixture(output)
            result = ArtifactBenchmark().evaluate(
                {"benchmark_spec": ""},
                output,
            )
            self.assertGreaterEqual(result.overall_score, 0.0)

            spec_path = output / "spec.json"
            spec_path.write_text(
                json.dumps({"expected_papers": [{"title": "Missing Paper"}]}),
                encoding="utf-8",
            )
            result = ArtifactBenchmark().evaluate({"benchmark_spec": str(spec_path)}, output)
            failures = (output / "benchmark_failures.jsonl").read_text(encoding="utf-8")

            self.assertGreater(result.failure_count, 0)
            self.assertIn("expected key papers retrieved", failures)

    @staticmethod
    def write_fixture(output: Path) -> None:
        paper = {
            "paper_id": "arxiv:1234_5678",
            "title": "A Retrieved Paper",
            "authors": "Ada Lovelace",
            "year": "2026",
            "venue": "arXiv",
            "doi": "",
            "arxiv_id": "1234.5678",
            "url": "https://arxiv.org/abs/1234.5678",
            "abstract": "We propose a neural field method.",
            "citation_count": "",
            "source": "arxiv",
        }
        for name in ["papers.csv", "ranked_papers.csv"]:
            with (output / name).open("w", encoding="utf-8", newline="") as handle:
                fieldnames = list(paper.keys())
                if name == "ranked_papers.csv":
                    fieldnames = ["rank", "decision", "score"] + fieldnames
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                row = dict(paper)
                if name == "ranked_papers.csv":
                    row.update({"rank": "1", "decision": "include", "score": "1.0"})
                writer.writerow(row)
        (output / "paper_readings.jsonl").write_text(
            json.dumps({"paper_id": "arxiv:1234_5678", "claims": ["neural field method"]}) + "\n",
            encoding="utf-8",
        )
        (output / "paper_sections.jsonl").write_text(
            json.dumps({"paper_id": "arxiv:1234_5678", "section_name": "method"}) + "\n",
            encoding="utf-8",
        )
        (output / "paper_tables.jsonl").write_text("", encoding="utf-8")
        (output / "paper_formulas.jsonl").write_text("", encoding="utf-8")
        evidence = {
            "evidence_id": "arxiv:1234_5678:claim:1",
            "paper_id": "arxiv:1234_5678",
            "claim": "neural field method",
        }
        (output / "evidence_store.jsonl").write_text(json.dumps(evidence) + "\n", encoding="utf-8")
        (output / "source_map.json").write_text(
            json.dumps({"evidence_sources": {"arxiv:1234_5678:claim:1": {"paper_id": "arxiv:1234_5678"}}}),
            encoding="utf-8",
        )
        (output / "report.md").write_text(
            "This report covers neural field evidence [arxiv:1234_5678:claim:1].",
            encoding="utf-8",
        )
        (output / "synthesis_summary.json").write_text(json.dumps({"paper_count": 1}), encoding="utf-8")
        (output / "verification_result.json").write_text(
            json.dumps({"checked_claim_count": 1, "unsupported_claim_count": 0}),
            encoding="utf-8",
        )
        (output / "unsupported_claims.jsonl").write_text("", encoding="utf-8")
        (output / "final_qa_result.json").write_text(
            json.dumps({"export_allowed": False, "blockers": ["not publication ready"]}),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
