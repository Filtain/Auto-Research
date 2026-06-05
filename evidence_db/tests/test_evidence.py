import json
import tempfile
import unittest
from pathlib import Path

from evidence_db.src.evidence import EvidenceExtractor


class EvidenceExtractorTests(unittest.TestCase):
    def test_extracts_evidence_store_and_source_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reading = {
                "paper_id": "arxiv:1234_5678",
                "paper_title": "A Retrieved Paper",
                "bibliographic_info": {
                    "authors": "Ada Lovelace",
                    "year": "2026",
                    "venue": "arXiv",
                    "url": "https://arxiv.org/abs/1234.5678",
                },
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

            result = EvidenceExtractor().extract_evidence(task_input={}, output_dir=output_dir)

            evidence_path = Path(result.evidence_store_jsonl)
            source_map_path = Path(result.source_map_json)
            self.assertTrue(evidence_path.exists())
            self.assertTrue(source_map_path.exists())
            self.assertEqual(result.paper_count, 1)
            self.assertEqual(result.evidence_count, 1)
            self.assertEqual(result.abstract_only_count, 1)

            evidence = json.loads(evidence_path.read_text(encoding="utf-8").strip())
            self.assertEqual(evidence["evidence_id"], "arxiv_1234_5678:claim:1")
            self.assertEqual(evidence["support_level"], "abstract_metadata_only")
            self.assertFalse(evidence["full_text_available"])
            self.assertEqual(evidence["source_location"]["section"], "abstract")
            self.assertIsNone(evidence["source_location"]["page"])

            source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
            self.assertIn("arxiv:1234_5678", source_map["papers"])
            self.assertIn("arxiv_1234_5678:claim:1", source_map["evidence_sources"])
            self.assertEqual(source_map["summary"]["evidence_count"], 1)

    def test_missing_paper_readings_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                EvidenceExtractor().extract_evidence(task_input={}, output_dir=Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
