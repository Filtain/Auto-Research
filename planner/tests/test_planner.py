import json
import tempfile
import unittest
from pathlib import Path

from planner.src.planner import Planner


class PlannerTests(unittest.TestCase):
    def test_generate_search_queries_writes_structured_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = Planner().generate_search_queries(
                {
                    "topic": "BANF band-limited neural fields NeRF LOD",
                    "research_questions": ["What problem does BANF solve?"],
                    "depth": "medium",
                },
                tmpdir,
            )

            path = Path(result.output_path)
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload["queries"]), 2)
            self.assertIn("inclusion_criteria", payload)
            self.assertEqual(payload["queries"][0]["purpose"], "primary_topic")


if __name__ == "__main__":
    unittest.main()
