import json
import tempfile
import unittest
from pathlib import Path

from promotion.src.promoter import PromotionWriter


class PromotionWriterTests(unittest.TestCase):
    def test_writes_promotion_and_ppt_outline_with_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            (output / "report.md").write_text("# Report\n\nEvidence-backed content.", encoding="utf-8")
            (output / "final_qa_result.json").write_text(json.dumps({"export_allowed": False}), encoding="utf-8")

            result = PromotionWriter().draft_promotion({}, output)
            ppt = (output / "ppt_outline.md").read_text(encoding="utf-8")

            self.assertEqual(result.artifact_count, 4)
            self.assertTrue((output / "promotion_brief.md").exists())
            self.assertTrue((output / "readme_draft.md").exists())
            self.assertIn("export_allowed=false", ppt)


if __name__ == "__main__":
    unittest.main()
