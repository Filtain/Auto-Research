import json
import tempfile
import unittest
from pathlib import Path

from comparison.src.comparator import MethodComparator


class MethodComparatorTests(unittest.TestCase):
    def test_compare_methods_writes_matrices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            evidence = {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "paper_title": "A Method Paper",
                "claim": "We propose a method and report PSNR results.",
                "claim_type": "author_claim",
            }
            (output_dir / "evidence_store.jsonl").write_text(
                json.dumps(evidence, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = MethodComparator().compare_methods(task_input={}, output_dir=output_dir)

            self.assertEqual(result.paper_count, 1)
            self.assertEqual(result.evidence_count, 1)
            self.assertTrue(Path(result.literature_matrix_csv).exists())
            self.assertTrue(Path(result.benchmark_matrix_csv).exists())
            self.assertTrue(Path(result.comparison_report_md).exists())


if __name__ == "__main__":
    unittest.main()
