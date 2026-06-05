import tempfile
import unittest
from pathlib import Path

from rebuttal.src.rebuttal import RebuttalPlanner


class RebuttalPlannerTests(unittest.TestCase):
    def test_without_comments_outputs_scaffold_not_fake_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)

            result = RebuttalPlanner().draft_rebuttal({}, output)
            response = (output / "response_to_reviewers.md").read_text(encoding="utf-8")

            self.assertEqual(result.comment_count, 0)
            self.assertTrue((output / "rebuttal_plan.md").exists())
            self.assertIn("No reviewer comments were provided", response)


if __name__ == "__main__":
    unittest.main()
