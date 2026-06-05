import json
import tempfile
import unittest
from pathlib import Path

from evaluation.src.evaluator import ResearchEvaluator


class ResearchEvaluatorTests(unittest.TestCase):
    def test_evaluates_missing_runs_as_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            (output / "verification_result.json").write_text(
                json.dumps(
                    {
                        "verification_passed": True,
                        "publication_ready": False,
                        "abstract_only_warning_count": 1,
                        "numeric_table_check_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            (output / "final_qa_result.json").write_text(
                json.dumps({"export_allowed": False}),
                encoding="utf-8",
            )

            result = ResearchEvaluator().evaluate_results({}, output)
            report = (output / "evaluation_report.md").read_text(encoding="utf-8")

            self.assertTrue((output / "missing_experiments.md").exists())
            self.assertTrue((output / "reviewer_risk_list.md").exists())
            self.assertGreaterEqual(result.risk_count, 1)
            self.assertIn("publication_ready: false", report)


if __name__ == "__main__":
    unittest.main()
