from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.src.evaluator import ArtifactBenchmark


@dataclass
class BenchmarkDatasetResult:
    dataset_metrics_json: str
    dataset_results_jsonl: str
    dataset_failures_jsonl: str
    dataset_leaderboard_csv: str
    dataset_report_md: str
    sample_count: int
    passed_count: int
    mean_score: float


class BenchmarkDatasetRunner:
    """Run artifact benchmarks over a dataset of Auto Research runs.

    Dataset format:

    ```json
    {
      "dataset_name": "demo",
      "samples": [
        {
          "sample_id": "demo_001",
          "run_dir": "output/demo_local_pdf",
          "benchmark_spec": "examples/demo/benchmark_spec.json",
          "split": "dev",
          "tags": ["offline", "demo"]
        }
      ]
    }
    ```

    The runner does not execute research pipelines. It evaluates already
    produced artifacts so that benchmark runs are deterministic and auditable.
    """

    def __init__(self, artifact_benchmark: ArtifactBenchmark | None = None) -> None:
        self.artifact_benchmark = artifact_benchmark or ArtifactBenchmark()

    def run_dataset(self, dataset_path: Path | str, output_dir: Path | str) -> BenchmarkDatasetResult:
        dataset_file = Path(dataset_path)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        dataset = self.read_json(dataset_file)
        samples = dataset.get("samples")
        if not isinstance(samples, list):
            raise ValueError("Benchmark dataset must contain a 'samples' list.")

        sample_results: list[dict[str, Any]] = []
        all_failures: list[dict[str, Any]] = []
        for index, raw_sample in enumerate(samples, start=1):
            if not isinstance(raw_sample, dict):
                raw_sample = {}
            sample = self.normalize_sample(raw_sample, dataset_file.parent, index=index)
            result = self.artifact_benchmark.evaluate(
                {"benchmark_spec": sample["benchmark_spec"]},
                sample["run_dir"],
            )
            scores = self.read_json(Path(result.benchmark_scores_json))
            layer_scores = {
                str(row.get("layer")): float(row.get("score", 0.0))
                for row in scores.get("layer_results", [])
                if isinstance(row, dict)
            }
            sample_payload = {
                "sample_id": sample["sample_id"],
                "split": sample["split"],
                "tags": sample["tags"],
                "run_dir": str(sample["run_dir"]),
                "benchmark_spec": str(sample["benchmark_spec"]),
                "overall_score": result.overall_score,
                "passed": result.passed,
                "failure_count": result.failure_count,
                "layer_scores": layer_scores,
            }
            sample_results.append(sample_payload)
            for failure in self.read_jsonl(Path(result.benchmark_failures_jsonl)):
                failure = dict(failure)
                failure["sample_id"] = sample["sample_id"]
                failure["split"] = sample["split"]
                all_failures.append(failure)

        metrics = self.aggregate_metrics(dataset, sample_results, all_failures)
        results_path = output_path / "benchmark_dataset_results.jsonl"
        failures_path = output_path / "benchmark_dataset_failures.jsonl"
        metrics_path = output_path / "benchmark_dataset_metrics.json"
        leaderboard_path = output_path / "benchmark_dataset_leaderboard.csv"
        report_path = output_path / "benchmark_dataset_report.md"

        self.write_jsonl(sample_results, results_path)
        self.write_jsonl(all_failures, failures_path)
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.write_leaderboard(sample_results, leaderboard_path)
        report_path.write_text(self.render_report(metrics, sample_results, all_failures), encoding="utf-8")
        return BenchmarkDatasetResult(
            dataset_metrics_json=str(metrics_path),
            dataset_results_jsonl=str(results_path),
            dataset_failures_jsonl=str(failures_path),
            dataset_leaderboard_csv=str(leaderboard_path),
            dataset_report_md=str(report_path),
            sample_count=int(metrics["sample_count"]),
            passed_count=int(metrics["passed_count"]),
            mean_score=float(metrics["mean_score"]),
        )

    @staticmethod
    def normalize_sample(raw_sample: dict[str, Any], dataset_root: Path, index: int) -> dict[str, Any]:
        sample_id = str(raw_sample.get("sample_id") or f"sample_{index}")
        run_dir_value = raw_sample.get("run_dir")
        if not run_dir_value:
            raise ValueError(f"Benchmark sample {sample_id} is missing run_dir.")
        run_dir = Path(str(run_dir_value))
        if not run_dir.is_absolute():
            run_dir = (dataset_root / run_dir).resolve()
        spec_value = raw_sample.get("benchmark_spec")
        spec_path = Path(str(spec_value)) if spec_value else run_dir / "benchmark_spec.json"
        if not spec_path.is_absolute():
            spec_path = (dataset_root / spec_path).resolve()
        tags = raw_sample.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        return {
            "sample_id": sample_id,
            "run_dir": run_dir,
            "benchmark_spec": spec_path,
            "split": str(raw_sample.get("split") or "default"),
            "tags": [str(tag) for tag in tags],
        }

    @staticmethod
    def aggregate_metrics(
        dataset: dict[str, Any],
        sample_results: list[dict[str, Any]],
        failures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sample_count = len(sample_results)
        passed_count = sum(1 for row in sample_results if row["passed"])
        mean_score = sum(float(row["overall_score"]) for row in sample_results) / max(1, sample_count)
        layer_names = sorted(
            {
                layer
                for row in sample_results
                for layer in row.get("layer_scores", {}).keys()
            }
        )
        layer_mean_scores = {
            layer: round(
                sum(float(row.get("layer_scores", {}).get(layer, 0.0)) for row in sample_results)
                / max(1, sample_count),
                4,
            )
            for layer in layer_names
        }
        split_metrics: dict[str, dict[str, Any]] = {}
        for row in sample_results:
            split = str(row["split"])
            entry = split_metrics.setdefault(split, {"sample_count": 0, "passed_count": 0, "score_sum": 0.0})
            entry["sample_count"] += 1
            entry["passed_count"] += int(bool(row["passed"]))
            entry["score_sum"] += float(row["overall_score"])
        for entry in split_metrics.values():
            entry["mean_score"] = round(entry["score_sum"] / max(1, entry["sample_count"]), 4)
            entry["pass_rate"] = round(entry["passed_count"] / max(1, entry["sample_count"]), 4)
            del entry["score_sum"]

        failure_by_layer: dict[str, int] = {}
        for failure in failures:
            layer = str(failure.get("layer") or "unknown")
            failure_by_layer[layer] = failure_by_layer.get(layer, 0) + 1

        return {
            "schema_version": "0.1",
            "benchmark_type": "dataset_artifact_quality",
            "dataset_name": str(dataset.get("dataset_name") or "unnamed_dataset"),
            "sample_count": sample_count,
            "passed_count": passed_count,
            "failed_count": sample_count - passed_count,
            "pass_rate": round(passed_count / max(1, sample_count), 4),
            "mean_score": round(mean_score, 4),
            "layer_mean_scores": layer_mean_scores,
            "split_metrics": split_metrics,
            "failure_count": len(failures),
            "failure_by_layer": failure_by_layer,
            "notes": [
                "Dataset benchmark evaluates already produced artifacts.",
                "Scores are comparable only when samples share a compatible benchmark spec policy.",
                "A high score is a confidence signal, not a proof of scientific correctness.",
            ],
        }

    @staticmethod
    def read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}

    @staticmethod
    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
        return rows

    @staticmethod
    def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def write_leaderboard(sample_results: list[dict[str, Any]], path: Path) -> None:
        layer_names = sorted(
            {
                layer
                for row in sample_results
                for layer in row.get("layer_scores", {}).keys()
            }
        )
        fieldnames = ["rank", "sample_id", "split", "overall_score", "passed", "failure_count"] + layer_names
        ranked = sorted(sample_results, key=lambda row: (-float(row["overall_score"]), str(row["sample_id"])))
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for rank, row in enumerate(ranked, start=1):
                payload = {
                    "rank": rank,
                    "sample_id": row["sample_id"],
                    "split": row["split"],
                    "overall_score": row["overall_score"],
                    "passed": str(row["passed"]).lower(),
                    "failure_count": row["failure_count"],
                }
                for layer in layer_names:
                    payload[layer] = row.get("layer_scores", {}).get(layer, "")
                writer.writerow(payload)

    @staticmethod
    def render_report(
        metrics: dict[str, Any],
        sample_results: list[dict[str, Any]],
        failures: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# Benchmark Dataset Report",
            "",
            "## Summary",
            "",
            f"- dataset_name: {metrics['dataset_name']}",
            f"- sample_count: {metrics['sample_count']}",
            f"- passed_count: {metrics['passed_count']}",
            f"- pass_rate: {metrics['pass_rate']}",
            f"- mean_score: {metrics['mean_score']}",
            f"- failure_count: {metrics['failure_count']}",
            "",
            "## Layer Mean Scores",
            "",
        ]
        for layer, score in metrics["layer_mean_scores"].items():
            lines.append(f"- {layer}: {score}")
        lines.extend(["", "## Samples", ""])
        for row in sorted(sample_results, key=lambda item: str(item["sample_id"])):
            lines.append(
                f"- `{row['sample_id']}` split={row['split']} score={row['overall_score']} passed={str(row['passed']).lower()}"
            )
        lines.extend(["", "## Failure Hotspots", ""])
        if metrics["failure_by_layer"]:
            for layer, count in sorted(metrics["failure_by_layer"].items()):
                lines.append(f"- {layer}: {count}")
        else:
            lines.append("- None.")
        lines.extend(["", "## Failure Samples", ""])
        if failures:
            for failure in failures[:50]:
                lines.append(
                    f"- `{failure.get('sample_id')}` [{failure.get('severity')}] {failure.get('layer')} / {failure.get('check')}: {failure.get('message')}"
                )
        else:
            lines.append("- None.")
        lines.extend(["", "## Notes", ""])
        for note in metrics["notes"]:
            lines.append(f"- {note}")
        return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Auto Research benchmark dataset evaluation.")
    parser.add_argument("--dataset", required=True, help="Path to benchmark dataset JSON.")
    parser.add_argument("--output-dir", default="output/benchmark_dataset", help="Directory for dataset metrics.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = BenchmarkDatasetRunner().run_dataset(dataset_path=args.dataset, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "dataset_metrics_json": result.dataset_metrics_json,
                "sample_count": result.sample_count,
                "passed_count": result.passed_count,
                "mean_score": result.mean_score,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
