import json
import tempfile
import unittest
from pathlib import Path

from idea_generation.src.generator import IdeaGenerator


class IdeaGeneratorTests(unittest.TestCase):
    def test_generates_proposal_only_ideas_from_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            (output / "synthesis_summary.json").write_text(
                json.dumps(
                    {
                        "research_gap_candidates": ["Current-run gap candidate: no full text."],
                        "method_taxonomy": [{"category": "neural_field", "evidence_ids": ["p1:claim:1"]}],
                    }
                ),
                encoding="utf-8",
            )
            (output / "evidence_store.jsonl").write_text(
                json.dumps({"evidence_id": "p1:claim:1", "claim": "A claim."}) + "\n",
                encoding="utf-8",
            )

            result = IdeaGenerator().generate_ideas({"max_ideas": 2}, output)
            payload = json.loads((output / "idea_candidates.json").read_text(encoding="utf-8"))

            self.assertTrue((output / "idea_candidates.md").exists())
            self.assertEqual(result.idea_count, 2)
            self.assertEqual(payload["ideas"][0]["claim_status"], "proposal_not_verified")
            self.assertIn("p1:claim:1", payload["ideas"][0]["supporting_evidence_ids"])


if __name__ == "__main__":
    unittest.main()
