import csv
import tempfile
import unittest
from pathlib import Path

from experiment.src.planner import ExperimentPlanner


class ExperimentPlannerTests(unittest.TestCase):
    def test_plan_experiments_writes_plan_and_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            matrix = output_dir / "literature_matrix.csv"
            with matrix.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["paper_id", "paper_title"])
                writer.writeheader()
                writer.writerow({"paper_id": "p1", "paper_title": "A Method Paper"})

            result = ExperimentPlanner().plan_experiments(task_input={}, output_dir=output_dir)

            self.assertGreater(result.item_count, 0)
            self.assertTrue(Path(result.experiment_plan_md).exists())
            self.assertTrue(Path(result.reproduction_checklist_csv).exists())
            self.assertTrue(Path(result.run_config_json).exists())


if __name__ == "__main__":
    unittest.main()
