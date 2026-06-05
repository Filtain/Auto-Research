from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ComparisonResult:
    literature_matrix_csv: str
    benchmark_matrix_csv: str
    comparison_report_md: str
    paper_count: int
    evidence_count: int


class MethodComparator:
    """Build conservative method and benchmark matrices from evidence."""

    def compare_methods(self, task_input: dict[str, Any], output_dir: Path | str) -> ComparisonResult:
        output_path = Path(output_dir)
        evidence_path = Path(str(task_input.get("evidence_store_jsonl") or output_path / "evidence_store.jsonl"))
        if not evidence_path.exists():
            raise FileNotFoundError(f"evidence_store.jsonl not found: {evidence_path}")
        evidence = self.read_jsonl(evidence_path)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in evidence:
            grouped[str(item.get("paper_id") or "unknown")].append(item)

        literature_path = output_path / "literature_matrix.csv"
        benchmark_path = output_path / "benchmark_matrix.csv"
        report_path = output_path / "comparison_report.md"
        self.write_literature_matrix(grouped, literature_path)
        self.write_benchmark_matrix(grouped, benchmark_path)
        self.write_report(grouped, report_path)
        return ComparisonResult(
            literature_matrix_csv=str(literature_path),
            benchmark_matrix_csv=str(benchmark_path),
            comparison_report_md=str(report_path),
            paper_count=len(grouped),
            evidence_count=len(evidence),
        )

    @staticmethod
    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
        return rows

    @staticmethod
    def write_literature_matrix(grouped: dict[str, list[dict[str, Any]]], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["paper_id", "paper_title", "method_claims", "finding_claims", "evidence_ids"],
            )
            writer.writeheader()
            for paper_id, items in sorted(grouped.items()):
                writer.writerow(
                    {
                        "paper_id": paper_id,
                        "paper_title": items[0].get("paper_title", ""),
                        "method_claims": " | ".join(
                            str(item.get("claim", ""))
                            for item in items
                            if item.get("claim_type") in {"author_claim", "metadata_summary"}
                        ),
                        "finding_claims": " | ".join(
                            str(item.get("claim", "")) for item in items if item.get("claim_type") == "finding"
                        ),
                        "evidence_ids": "; ".join(str(item.get("evidence_id", "")) for item in items),
                    }
                )

    @staticmethod
    def write_benchmark_matrix(grouped: dict[str, list[dict[str, Any]]], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["paper_id", "paper_title", "datasets_or_metrics_found", "evidence_ids", "note"],
            )
            writer.writeheader()
            for paper_id, items in sorted(grouped.items()):
                benchmark_items = [
                    item for item in items if any(term in str(item.get("claim", "")).lower() for term in [
                        "dataset", "benchmark", "psnr", "ssim", "lpips", "accuracy", "result"
                    ])
                ]
                writer.writerow(
                    {
                        "paper_id": paper_id,
                        "paper_title": items[0].get("paper_title", ""),
                        "datasets_or_metrics_found": " | ".join(str(item.get("claim", "")) for item in benchmark_items),
                        "evidence_ids": "; ".join(str(item.get("evidence_id", "")) for item in benchmark_items),
                        "note": "No benchmark evidence extracted." if not benchmark_items else "Evidence-backed benchmark hints only.",
                    }
                )

    @staticmethod
    def write_report(grouped: dict[str, list[dict[str, Any]]], path: Path) -> None:
        lines = [
            "# Comparison Report",
            "",
            f"- papers_compared: {len(grouped)}",
            "",
            "## Notes",
            "",
            "- Matrices are built from extracted evidence only.",
            "- Empty benchmark cells mean no benchmark evidence was extracted, not that the paper lacks benchmarks.",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
