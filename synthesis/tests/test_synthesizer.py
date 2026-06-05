import json
import tempfile
import unittest
from pathlib import Path

from synthesis.src.synthesizer import FindingsSynthesizer


class FindingsSynthesizerTests(unittest.TestCase):
    def test_synthesizes_report_and_summary_from_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            evidence = {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "paper_title": "A Retrieved Paper",
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
                        "paper_title": "A Retrieved Paper",
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

            result = FindingsSynthesizer().synthesize_findings(task_input={}, output_dir=output_dir)

            report_path = Path(result.report_md)
            summary_path = Path(result.synthesis_summary_json)
            self.assertTrue(report_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertEqual(result.evidence_count, 1)
            self.assertEqual(result.paper_count, 1)
            self.assertEqual(result.claim_type_count["author_claim"], 1)
            self.assertEqual(result.abstract_only_evidence_count, 1)

            report = report_path.read_text(encoding="utf-8")
            self.assertIn("p1:claim:1", report)
            self.assertIn("abstract_metadata_only", report)
            self.assertIn("We propose a neural field method.", report)

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["evidence_count"], 1)
            self.assertIn("Current synthesis is based only on title/abstract metadata.", summary["coverage_gaps"])

    def test_missing_evidence_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "source_map.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                FindingsSynthesizer().synthesize_findings(task_input={}, output_dir=output_dir)


if __name__ == "__main__":
    unittest.main()
