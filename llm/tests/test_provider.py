import json
import tempfile
import unittest
from pathlib import Path

from llm.src.provider import LLMClient


class LLMClientTests(unittest.TestCase):
    def test_deterministic_provider_logs_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = LLMClient(provider="deterministic", model="none").complete("hello", tmpdir)

            self.assertIn("Prompt length", result.text)
            log_path = Path(tmpdir) / "llm_calls.jsonl"
            self.assertTrue(log_path.exists())
            row = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["provider"], "deterministic")


if __name__ == "__main__":
    unittest.main()
