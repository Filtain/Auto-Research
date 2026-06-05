import json
import tempfile
import unittest
from pathlib import Path

from final_qa.src.final_gate import FinalQAGate


class FinalQAGateTests(unittest.TestCase):
    def write_required_artifacts(self, output_dir: Path, verification: dict) -> None:
        for name in FinalQAGate.REQUIRED_ARTIFACTS:
            path = output_dir / name
            if name == "verification_result.json":
                path.write_text(json.dumps(verification, ensure_ascii=False), encoding="utf-8")
            else:
                path.write_text("content\n", encoding="utf-8")

    def test_blocks_export_when_abstract_only_not_publication_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            self.write_required_artifacts(
                output_dir,
                {
                    "verification_passed": True,
                    "publication_ready": False,
                    "checked_claim_count": 1,
                    "unsupported_claim_count": 0,
                    "missing_evidence_count": 0,
                    "abstract_only_warning_count": 1,
                },
            )

            result = FinalQAGate().run_final_qa(task_input={}, output_dir=output_dir)

            self.assertTrue(Path(result.final_qa_report_md).exists())
            self.assertTrue(Path(result.final_qa_result_json).exists())
            self.assertFalse(result.export_allowed)
            self.assertFalse(result.publication_ready)
            self.assertGreater(result.blocker_count, 0)
            self.assertEqual(result.warning_count, 1)

    def test_allows_export_when_verification_is_publication_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            self.write_required_artifacts(
                output_dir,
                {
                    "verification_passed": True,
                    "publication_ready": True,
                    "checked_claim_count": 1,
                    "unsupported_claim_count": 0,
                    "missing_evidence_count": 0,
                    "abstract_only_warning_count": 0,
                },
            )

            result = FinalQAGate().run_final_qa(task_input={}, output_dir=output_dir)

            self.assertTrue(result.export_allowed)
            self.assertTrue(result.publication_ready)
            self.assertEqual(result.blocker_count, 0)

    def test_missing_verification_result_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                FinalQAGate().run_final_qa(task_input={}, output_dir=Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
