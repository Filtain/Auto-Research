import json
import tempfile
import unittest
from pathlib import Path

from method_design.src.designer import MethodDesigner


class MethodDesignerTests(unittest.TestCase):
    def test_writes_method_spec_and_ablation_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            (output / "idea_candidates.json").write_text(
                json.dumps(
                    {
                        "ideas": [
                            {
                                "idea_id": "idea_1",
                                "title": "Test idea",
                                "motivation": "Evidence-backed gap.",
                                "supporting_evidence_ids": ["p1:claim:1"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = MethodDesigner().design_method({}, output)
            spec = json.loads((output / "method_spec.json").read_text(encoding="utf-8"))

            self.assertTrue((output / "method_spec.md").exists())
            self.assertTrue((output / "ablation_plan.md").exists())
            self.assertEqual(result.component_count, 3)
            self.assertEqual(spec["status"], "proposed_method_not_validated")


if __name__ == "__main__":
    unittest.main()
