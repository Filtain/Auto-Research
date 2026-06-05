import json
import sys
import tempfile
import unittest
from pathlib import Path

from experiment.src.runner import ExperimentRunner


class ExperimentRunnerTests(unittest.TestCase):
    def test_run_experiments_defaults_to_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "run_config.json").write_text(
                json.dumps(
                    {
                        "dry_run": True,
                        "experiments": [
                            {"id": "exp_1", "name": "Smoke", "command": [sys.executable, "-c", "print('run')"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = ExperimentRunner().run_experiments(task_input={}, output_dir=output_dir)

            self.assertEqual(result.run_count, 1)
            self.assertEqual(result.dry_run_count, 1)
            self.assertTrue(Path(result.experiment_runs_jsonl).exists())
            self.assertTrue(Path(result.results_table_csv).exists())
            self.assertTrue(Path(result.experiment_run_report_md).exists())

    def test_run_experiments_executes_when_dry_run_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "run_config.json").write_text(
                json.dumps(
                    {
                        "dry_run": False,
                        "experiments": [
                            {"id": "exp_1", "name": "Smoke", "command": [sys.executable, "-c", "print('ok')"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = ExperimentRunner().run_experiments(task_input={"dry_run": False}, output_dir=output_dir)
            run_record = json.loads(Path(result.experiment_runs_jsonl).read_text(encoding="utf-8").strip())

            self.assertEqual(result.completed_count, 1)
            self.assertEqual(run_record["status"], "completed")
            self.assertIn("ok", Path(run_record["stdout_path"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
