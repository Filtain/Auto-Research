from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExperimentPlanResult:
    experiment_plan_md: str
    reproduction_checklist_csv: str
    run_config_json: str
    item_count: int


class ExperimentPlanner:
    """Create a conservative reproducibility plan from comparison artifacts."""

    def plan_experiments(self, task_input: dict[str, Any], output_dir: Path | str) -> ExperimentPlanResult:
        output_path = Path(output_dir)
        literature_path = Path(str(task_input.get("literature_matrix_csv") or output_path / "literature_matrix.csv"))
        rows = self.read_csv(literature_path) if literature_path.exists() else []
        checklist_path = output_path / "reproduction_checklist.csv"
        plan_path = output_path / "experiment_plan.md"
        run_config_path = output_path / "run_config.json"
        checklist = self.checklist(rows)
        self.write_checklist(checklist, checklist_path)
        self.write_plan(rows, checklist, plan_path)
        self.write_run_config(task_input, run_config_path)
        return ExperimentPlanResult(
            experiment_plan_md=str(plan_path),
            reproduction_checklist_csv=str(checklist_path),
            run_config_json=str(run_config_path),
            item_count=len(checklist),
        )

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    @staticmethod
    def checklist(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        base = [
            ("source_code", "Find official implementation or faithful reproduction."),
            ("environment", "Record Python/CUDA/framework versions."),
            ("data", "Identify datasets and download instructions."),
            ("metrics", "Define metrics exactly as reported."),
            ("baseline", "Select baseline methods from evidence-backed comparison."),
            ("compute", "Estimate GPU/CPU requirements."),
            ("risk", "Mark missing full-text or benchmark evidence."),
        ]
        return [
            {"item": key, "action": action, "status": "pending", "source_papers": str(len(rows))}
            for key, action in base
        ]

    @staticmethod
    def write_checklist(rows: list[dict[str, str]], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["item", "action", "status", "source_papers"])
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def write_plan(rows: list[dict[str, str]], checklist: list[dict[str, str]], path: Path) -> None:
        lines = [
            "# Experiment Plan",
            "",
            f"- source_papers_in_matrix: {len(rows)}",
            f"- checklist_items: {len(checklist)}",
            "",
            "## Reproducibility Checklist",
            "",
        ]
        for item in checklist:
            lines.append(f"- [{item['status']}] {item['item']}: {item['action']}")
        lines.extend(
            [
                "",
                "## Anti-Hallucination Notes",
                "",
                "- This is a plan only; no experimental results are fabricated.",
                "- Missing benchmark evidence remains a blocker for exact reproduction.",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def write_run_config(task_input: dict[str, Any], path: Path) -> None:
        commands = task_input.get("experiment_commands") or []
        if not isinstance(commands, list):
            commands = []
        experiments: list[dict[str, Any]] = []
        for index, command in enumerate(commands, start=1):
            if isinstance(command, str):
                experiments.append({"id": f"exp_{index}", "name": f"Experiment {index}", "command": command})
            elif isinstance(command, dict):
                experiments.append(
                    {
                        "id": str(command.get("id") or f"exp_{index}"),
                        "name": str(command.get("name") or f"Experiment {index}"),
                        "command": command.get("command") or [],
                        "cwd": str(command.get("cwd") or ""),
                        "env": command.get("env") if isinstance(command.get("env"), dict) else {},
                    }
                )
        payload = {
            "schema_version": "0.1",
            "dry_run": bool(task_input.get("dry_run", True)),
            "timeout_seconds": int(task_input.get("timeout_seconds", 300)),
            "experiments": experiments,
            "notes": [
                "Commands are not scientific results by themselves.",
                "Only executed command logs and return codes should be treated as run evidence.",
                "Default dry_run=true prevents accidental execution.",
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
