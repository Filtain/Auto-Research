from __future__ import annotations

import csv
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ExperimentRunResult:
    experiment_runs_jsonl: str
    results_table_csv: str
    experiment_run_report_md: str
    run_count: int
    completed_count: int
    failed_count: int
    dry_run_count: int


class ExperimentRunner:
    """Run explicitly configured experiment commands and record real outputs."""

    def run_experiments(self, task_input: dict[str, Any], output_dir: Path | str) -> ExperimentRunResult:
        output_path = Path(output_dir)
        config_path = Path(str(task_input.get("run_config_json") or output_path / "run_config.json"))
        if not config_path.exists():
            raise FileNotFoundError(f"run_config.json not found: {config_path}")

        config = json.loads(config_path.read_text(encoding="utf-8"))
        experiments = config.get("experiments") if isinstance(config, dict) else []
        if not isinstance(experiments, list):
            experiments = []
        dry_run = bool(task_input.get("dry_run", config.get("dry_run", True)))
        timeout_seconds = int(task_input.get("timeout_seconds", config.get("timeout_seconds", 300)))

        logs_dir = output_path / "experiment_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        run_records: list[dict[str, Any]] = []
        for index, experiment in enumerate(experiments, start=1):
            if not isinstance(experiment, dict):
                continue
            record = self.run_one(
                experiment=experiment,
                index=index,
                output_dir=output_path,
                logs_dir=logs_dir,
                dry_run=dry_run,
                timeout_seconds=timeout_seconds,
            )
            run_records.append(record)

        runs_path = output_path / "experiment_runs.jsonl"
        results_path = output_path / "results_table.csv"
        report_path = output_path / "experiment_run_report.md"
        self.write_jsonl(run_records, runs_path)
        self.write_results_table(run_records, results_path)
        self.write_report(run_records, report_path, dry_run=dry_run)

        return ExperimentRunResult(
            experiment_runs_jsonl=str(runs_path),
            results_table_csv=str(results_path),
            experiment_run_report_md=str(report_path),
            run_count=len(run_records),
            completed_count=sum(1 for record in run_records if record["status"] == "completed"),
            failed_count=sum(1 for record in run_records if record["status"] == "failed"),
            dry_run_count=sum(1 for record in run_records if record["status"] == "dry_run"),
        )

    def run_one(
        self,
        experiment: dict[str, Any],
        index: int,
        output_dir: Path,
        logs_dir: Path,
        dry_run: bool,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        experiment_id = str(experiment.get("id") or f"exp_{index}")
        command = experiment.get("command") or []
        command_display = command if isinstance(command, str) else " ".join(str(part) for part in command)
        stdout_path = logs_dir / f"{experiment_id}.stdout.txt"
        stderr_path = logs_dir / f"{experiment_id}.stderr.txt"
        started_at = self.now()
        if dry_run:
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("dry_run=true; command was not executed.\n", encoding="utf-8")
            return {
                "experiment_id": experiment_id,
                "name": str(experiment.get("name") or experiment_id),
                "command": command_display,
                "status": "dry_run",
                "return_code": "",
                "started_at": started_at,
                "finished_at": self.now(),
                "duration_seconds": 0.0,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "error": "",
            }

        argv = self.normalize_command(command)
        cwd = self.resolve_cwd(experiment.get("cwd"), output_dir)
        env = experiment.get("env") if isinstance(experiment.get("env"), dict) else None
        merged_env = None if env is None else {**os.environ, **{str(key): str(value) for key, value in env.items()}}
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                env=merged_env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            stdout_path.write_text(completed.stdout, encoding="utf-8")
            stderr_path.write_text(completed.stderr, encoding="utf-8")
            status = "completed" if completed.returncode == 0 else "failed"
            return_code: int | str = completed.returncode
            error = ""
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
            status = "failed"
            return_code = ""
            error = f"Command timed out after {timeout_seconds} seconds."
        except Exception as exc:  # noqa: BLE001 - persist execution failure.
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(str(exc), encoding="utf-8")
            status = "failed"
            return_code = ""
            error = str(exc)

        return {
            "experiment_id": experiment_id,
            "name": str(experiment.get("name") or experiment_id),
            "command": command_display,
            "status": status,
            "return_code": return_code,
            "started_at": started_at,
            "finished_at": self.now(),
            "duration_seconds": 0.0,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "error": error,
        }

    @staticmethod
    def normalize_command(command: Any) -> list[str]:
        if isinstance(command, list):
            return [str(part) for part in command]
        if isinstance(command, str):
            return shlex.split(command)
        raise ValueError("Experiment command must be a string or list.")

    @staticmethod
    def resolve_cwd(cwd: Any, output_dir: Path) -> Path:
        if not cwd:
            return output_dir
        path = Path(str(cwd))
        return path if path.is_absolute() else output_dir / path

    @staticmethod
    def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def write_results_table(records: list[dict[str, Any]], path: Path) -> None:
        fieldnames = [
            "experiment_id",
            "name",
            "status",
            "return_code",
            "command",
            "stdout_path",
            "stderr_path",
            "error",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow({field: record.get(field, "") for field in fieldnames})

    @staticmethod
    def write_report(records: list[dict[str, Any]], path: Path, dry_run: bool) -> None:
        lines = [
            "# Experiment Run Report",
            "",
            f"- run_count: {len(records)}",
            f"- completed_count: {sum(1 for record in records if record['status'] == 'completed')}",
            f"- failed_count: {sum(1 for record in records if record['status'] == 'failed')}",
            f"- dry_run_count: {sum(1 for record in records if record['status'] == 'dry_run')}",
            f"- dry_run_mode: {str(dry_run).lower()}",
            "",
            "## Runs",
            "",
        ]
        if not records:
            lines.append("- No experiment commands were configured.")
        for record in records:
            lines.append(
                f"- `{record['experiment_id']}` {record['status']} return_code={record['return_code']} command=`{record['command']}`"
            )
        lines.extend(
            [
                "",
                "## Anti-Hallucination Notes",
                "",
                "- This report records execution status only.",
                "- Scientific metrics must be parsed from real output files before being reported as results.",
                "- Dry-run records are not executed experiments.",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
