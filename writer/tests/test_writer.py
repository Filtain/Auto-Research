import tempfile
import unittest
from pathlib import Path

from writer.src.writer import ResearchWriter


class ResearchWriterTests(unittest.TestCase):
    def test_draft_paper_writes_final_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "report.md").write_text("# Report\n", encoding="utf-8")
            (output_dir / "verification_report.md").write_text("# Verification\n", encoding="utf-8")

            result = ResearchWriter().draft_paper(task_input={}, output_dir=output_dir)

            self.assertTrue(Path(result.final_report_md).exists())
            self.assertGreaterEqual(result.section_count, 2)
            self.assertIn("Auto Research Final Report", Path(result.final_report_md).read_text(encoding="utf-8"))
            self.assertFalse(Path(result.llm_call_log_jsonl).exists())

    def test_draft_paper_can_use_deterministic_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "report.md").write_text("# Report\n", encoding="utf-8")
            (output_dir / "verification_report.md").write_text("# Verification\n", encoding="utf-8")

            result = ResearchWriter().draft_paper(task_input={"use_llm": True}, output_dir=output_dir)

            self.assertTrue(Path(result.llm_call_log_jsonl).exists())
            report_text = Path(result.final_report_md).read_text(encoding="utf-8")
            self.assertIn("LLM-Assisted Executive Summary", report_text)
            self.assertIn("Deterministic LLM fallback", report_text)


if __name__ == "__main__":
    unittest.main()
