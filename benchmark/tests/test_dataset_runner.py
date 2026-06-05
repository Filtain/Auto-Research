import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.src.dataset_runner import BenchmarkDatasetRunner


class BenchmarkDatasetRunnerTests(unittest.TestCase):
    def test_runs_dataset_and_writes_aggregate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_a = root / "run_a"
            run_b = root / "run_b"
            run_a.mkdir()
            run_b.mkdir()
            write_fixture(run_a)
            write_fixture(run_b)
            spec_a = root / "spec_a.json"
            spec_b = root / "spec_b.json"
            spec_a.write_text(
                json.dumps(
                    {
                        "expected_papers": [{"title": "A Retrieved Paper"}],
                        "expected_sections": ["method"],
                        "required_synthesis_topics": ["neural field"],
                        "expected_unsupported_claim_count": 0,
                        "expected_export_allowed": False,
                        "expected_safe_export": False,
                    }
                ),
                encoding="utf-8",
            )
            spec_b.write_text(
                json.dumps({"expected_papers": [{"title": "Missing Paper"}]}),
                encoding="utf-8",
            )
            dataset_path = root / "dataset.json"
            dataset_path.write_text(
                json.dumps(
                    {
                        "dataset_name": "unit_dataset",
                        "samples": [
                            {
                                "sample_id": "sample_a",
                                "run_dir": str(run_a),
                                "benchmark_spec": str(spec_a),
                                "split": "dev",
                                "tags": ["positive"],
                            },
                            {
                                "sample_id": "sample_b",
                                "run_dir": str(run_b),
                                "benchmark_spec": str(spec_b),
                                "split": "dev",
                                "tags": ["negative"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = BenchmarkDatasetRunner().run_dataset(dataset_path, root / "dataset_output")
            metrics = json.loads(Path(result.dataset_metrics_json).read_text(encoding="utf-8"))

            self.assertEqual(result.sample_count, 2)
            self.assertEqual(metrics["dataset_name"], "unit_dataset")
            self.assertIn("retrieval", metrics["layer_mean_scores"])
            self.assertTrue(Path(result.dataset_results_jsonl).exists())
            self.assertTrue(Path(result.dataset_failures_jsonl).exists())
            self.assertTrue(Path(result.dataset_report_md).exists())
            with Path(result.dataset_leaderboard_csv).open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["sample_id"], "sample_a")

    def test_dataset_requires_samples_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dataset_path = root / "dataset.json"
            dataset_path.write_text(json.dumps({"dataset_name": "bad"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                BenchmarkDatasetRunner().run_dataset(dataset_path, root / "out")

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
