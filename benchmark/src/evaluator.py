from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkResult:
    benchmark_report_md: str
    benchmark_scores_json: str
    benchmark_failures_jsonl: str
    benchmark_summary_csv: str
    overall_score: float
    passed: bool
    layer_count: int
    failure_count: int


class ArtifactBenchmark:
    """Evaluate Auto Research artifact quality layer by layer.

    This benchmark scores pipeline artifacts, not just natural-language output.
    If a ground-truth spec is provided, the evaluator checks expected papers,
    evidence IDs, required synthesis topics, unsupported-claim handling, and QA
    gating. Without a spec, it runs conservative artifact completeness checks.
    """

    LAYERS = [
        "retrieval",
        "triage",
        "reading",
        "evidence",
        "synthesis",
        "verification",
        "final_qa",
        "end_to_end",
    ]

    def evaluate(self, task_input: dict[str, Any], output_dir: Path | str) -> BenchmarkResult:
        output_path = Path(output_dir)
        spec_path_value = task_input.get("benchmark_spec")
        spec_path = Path(str(spec_path_value)) if spec_path_value else output_path / "benchmark_spec.json"
        spec = self.read_json(spec_path) if spec_path.exists() else {}

        layer_results = [
            self.evaluate_retrieval(output_path, spec),
            self.evaluate_triage(output_path, spec),
            self.evaluate_reading(output_path, spec),
            self.evaluate_evidence(output_path, spec),
            self.evaluate_synthesis(output_path, spec),
            self.evaluate_verification(output_path, spec),
            self.evaluate_final_qa(output_path, spec),
            self.evaluate_end_to_end(output_path, spec),
        ]
        failures = [
            {
                "layer": result["layer"],
                "check": check["name"],
                "severity": check["severity"],
                "message": check["message"],
            }
            for result in layer_results
            for check in result["checks"]
            if not check["passed"]
        ]
        overall = sum(float(result["score"]) for result in layer_results) / max(1, len(layer_results))
        pass_threshold = float(spec.get("pass_threshold", task_input.get("pass_threshold", 0.75)) or 0.75)
        critical_failures = [item for item in failures if item["severity"] == "critical"]
        passed = overall >= pass_threshold and not critical_failures

        payload = {
            "schema_version": "0.1",
            "benchmark_type": "artifact_quality",
            "spec_path": str(spec_path) if spec_path.exists() else "",
            "has_ground_truth_spec": bool(spec),
            "pass_threshold": pass_threshold,
            "overall_score": round(overall, 4),
            "passed": passed,
            "layer_results": layer_results,
            "failure_count": len(failures),
            "critical_failure_count": len(critical_failures),
            "notes": [
                "Scores evaluate produced artifacts and traceability, not scientific truth by themselves.",
                "Missing ground-truth spec limits this to artifact sanity checks.",
                "A passed benchmark is a confidence signal, not publication acceptance.",
            ],
        }

        report_path = output_path / "benchmark_report.md"
        scores_path = output_path / "benchmark_scores.json"
        failures_path = output_path / "benchmark_failures.jsonl"
        summary_path = output_path / "benchmark_summary.csv"
        scores_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.write_jsonl(failures, failures_path)
        self.write_summary_csv(layer_results, summary_path)
        report_path.write_text(self.render_report(payload, failures), encoding="utf-8")
        return BenchmarkResult(
            benchmark_report_md=str(report_path),
            benchmark_scores_json=str(scores_path),
            benchmark_failures_jsonl=str(failures_path),
            benchmark_summary_csv=str(summary_path),
            overall_score=round(overall, 4),
            passed=passed,
            layer_count=len(layer_results),
            failure_count=len(failures),
        )

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
    def read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    @staticmethod
    def text(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def evaluate_retrieval(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        rows = self.read_csv(output_path / "papers.csv")
        expected = self.expected_papers(spec)
        identifiers = self.paper_identifiers(rows)
        checks = [self.check("papers.csv exists and is non-empty", bool(rows), "critical")]
        if expected:
            found = sum(1 for paper in expected if self.paper_match(paper, identifiers))
            checks.append(
                self.check(
                    "expected key papers retrieved",
                    found == len(expected),
                    "critical",
                    f"found {found}/{len(expected)} expected papers",
                    partial=found / max(1, len(expected)),
                )
            )
        return self.layer("retrieval", checks)

    def evaluate_triage(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        rows = self.read_csv(output_path / "ranked_papers.csv")
        expected = self.expected_papers(spec)
        checks = [self.check("ranked_papers.csv exists and is non-empty", bool(rows), "critical")]
        top_k = int(spec.get("triage_top_k", 5) or 5)
        if expected and rows:
            top_rows = rows[:top_k]
            identifiers = self.paper_identifiers(top_rows)
            found = sum(1 for paper in expected if self.paper_match(paper, identifiers))
            checks.append(
                self.check(
                    f"expected key papers appear in top {top_k}",
                    found == len(expected),
                    "high",
                    f"found {found}/{len(expected)} expected papers in top {top_k}",
                    partial=found / max(1, len(expected)),
                )
            )
        return self.layer("triage", checks)

    def evaluate_reading(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        readings = self.read_jsonl(output_path / "paper_readings.jsonl")
        sections = self.read_jsonl(output_path / "paper_sections.jsonl")
        tables = self.read_jsonl(output_path / "paper_tables.jsonl")
        formulas = self.read_jsonl(output_path / "paper_formulas.jsonl")
        checks = [self.check("paper_readings.jsonl exists and is non-empty", bool(readings), "critical")]
        expected_sections = [str(item).lower() for item in spec.get("expected_sections", []) if str(item).strip()]
        if expected_sections:
            section_text = " ".join(str(row.get("section_name") or row.get("heading") or row) for row in sections).lower()
            found = sum(1 for section in expected_sections if section in section_text)
            checks.append(
                self.check(
                    "expected sections extracted",
                    found == len(expected_sections),
                    "high",
                    f"found {found}/{len(expected_sections)} expected sections",
                    partial=found / max(1, len(expected_sections)),
                )
            )
        if spec.get("expect_tables"):
            checks.append(self.check("table candidates extracted", bool(tables), "medium"))
        if spec.get("expect_formulas"):
            checks.append(self.check("formula candidates extracted", bool(formulas), "medium"))
        return self.layer("reading", checks)

    def evaluate_evidence(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        evidence = self.read_jsonl(output_path / "evidence_store.jsonl")
        source_map = self.read_json(output_path / "source_map.json") if (output_path / "source_map.json").exists() else {}
        source_entries = source_map.get("evidence_sources") if isinstance(source_map, dict) else {}
        checks = [
            self.check("evidence_store.jsonl exists and is non-empty", bool(evidence), "critical"),
            self.check("source_map.json has evidence_sources", isinstance(source_entries, dict) and bool(source_entries), "critical"),
        ]
        evidence_ids = {str(item.get("evidence_id") or "") for item in evidence}
        missing_source = [
            evidence_id for evidence_id in evidence_ids if evidence_id and evidence_id not in source_entries
        ]
        if evidence:
            checks.append(
                self.check(
                    "every evidence ID has source mapping",
                    not missing_source,
                    "critical",
                    f"missing source mappings: {len(missing_source)}",
                    partial=(len(evidence_ids) - len(missing_source)) / max(1, len(evidence_ids)),
                )
            )
        expected_ids = [str(item) for item in spec.get("expected_evidence_ids", []) if str(item).strip()]
        if expected_ids:
            found = sum(1 for evidence_id in expected_ids if evidence_id in evidence_ids)
            checks.append(
                self.check(
                    "expected evidence IDs present",
                    found == len(expected_ids),
                    "high",
                    f"found {found}/{len(expected_ids)} expected evidence IDs",
                    partial=found / max(1, len(expected_ids)),
                )
            )
        return self.layer("evidence", checks)

    def evaluate_synthesis(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        report = self.text(output_path / "report.md")
        summary = self.read_json(output_path / "synthesis_summary.json") if (output_path / "synthesis_summary.json").exists() else {}
        checks = [
            self.check("report.md exists and is non-empty", bool(report.strip()), "critical"),
            self.check("synthesis_summary.json exists", bool(summary), "critical"),
        ]
        required_topics = [str(item).lower() for item in spec.get("required_synthesis_topics", []) if str(item).strip()]
        if required_topics:
            report_lower = report.lower()
            found = sum(1 for topic in required_topics if topic in report_lower)
            checks.append(
                self.check(
                    "required synthesis topics covered",
                    found == len(required_topics),
                    "high",
                    f"found {found}/{len(required_topics)} required topics",
                    partial=found / max(1, len(required_topics)),
                )
            )
        if report:
            checks.append(
                self.check(
                    "report includes evidence ID references",
                    bool(re.search(r"\[[A-Za-z0-9_.:-]+:claim:\d+\]", report)),
                    "critical",
                )
            )
        return self.layer("synthesis", checks)

    def evaluate_verification(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        result = self.read_json(output_path / "verification_result.json") if (output_path / "verification_result.json").exists() else {}
        unsupported = self.read_jsonl(output_path / "unsupported_claims.jsonl")
        expected_unsupported = int(spec.get("expected_unsupported_claim_count", 0) or 0)
        checks = [self.check("verification_result.json exists", bool(result), "critical")]
        if result:
            checks.extend(
                [
                    self.check("verification checked at least one claim", int(result.get("checked_claim_count", 0)) > 0, "critical"),
                    self.check(
                        "unsupported claim count matches expected policy",
                        int(result.get("unsupported_claim_count", 0)) == expected_unsupported,
                        "critical" if expected_unsupported == 0 else "high",
                        f"actual={result.get('unsupported_claim_count', 0)} expected={expected_unsupported}",
                    ),
                    self.check(
                        "unsupported_claims.jsonl matches verification count",
                        len(unsupported) == int(result.get("unsupported_claim_count", 0)),
                        "high",
                    ),
                ]
            )
        return self.layer("verification", checks)

    def evaluate_final_qa(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        result = self.read_json(output_path / "final_qa_result.json") if (output_path / "final_qa_result.json").exists() else {}
        checks = [self.check("final_qa_result.json exists", bool(result), "critical")]
        if result and "expected_export_allowed" in spec:
            expected = bool(spec.get("expected_export_allowed"))
            checks.append(
                self.check(
                    "Final QA export decision matches expected safety policy",
                    bool(result.get("export_allowed")) == expected,
                    "critical",
                    f"actual={result.get('export_allowed')} expected={expected}",
                )
            )
        if result:
            checks.append(
                self.check(
                    "Final QA reports blockers or allows export",
                    bool(result.get("export_allowed")) or bool(result.get("blockers")),
                    "high",
                )
            )
        return self.layer("final_qa", checks)

    def evaluate_end_to_end(self, output_path: Path, spec: dict[str, Any]) -> dict[str, Any]:
        required = [
            "papers.csv",
            "ranked_papers.csv",
            "paper_readings.jsonl",
            "evidence_store.jsonl",
            "source_map.json",
            "report.md",
            "verification_result.json",
            "final_qa_result.json",
        ]
        missing = [name for name in required if not (output_path / name).exists()]
        checks = [
            self.check(
                "required end-to-end artifacts exist",
                not missing,
                "critical",
                f"missing: {', '.join(missing) if missing else 'none'}",
                partial=(len(required) - len(missing)) / len(required),
            )
        ]
        if "expected_safe_export" in spec:
            final_qa = self.read_json(output_path / "final_qa_result.json") if (output_path / "final_qa_result.json").exists() else {}
            checks.append(
                self.check(
                    "end-to-end safe export matches expected policy",
                    bool(final_qa.get("export_allowed")) == bool(spec.get("expected_safe_export")),
                    "critical",
                )
            )
        return self.layer("end_to_end", checks)

    @staticmethod
    def expected_papers(spec: dict[str, Any]) -> list[dict[str, str]]:
        values = spec.get("expected_papers", [])
        if not isinstance(values, list):
            return []
        rows: list[dict[str, str]] = []
        for value in values:
            if isinstance(value, str):
                rows.append({"title": value})
            elif isinstance(value, dict):
                rows.append({str(key): str(item) for key, item in value.items()})
        return rows

    @staticmethod
    def paper_identifiers(rows: list[dict[str, str]]) -> list[str]:
        identifiers = []
        for row in rows:
            identifiers.append(
                " ".join(
                    str(row.get(field, "")).lower()
                    for field in ["paper_id", "title", "doi", "arxiv_id", "url"]
                )
            )
        return identifiers

    @staticmethod
    def paper_match(expected: dict[str, str], identifiers: list[str]) -> bool:
        candidates = [
            str(expected.get("paper_id", "")),
            str(expected.get("title", "")),
            str(expected.get("doi", "")),
            str(expected.get("arxiv_id", "")),
            str(expected.get("url", "")),
        ]
        candidates = [candidate.lower().strip() for candidate in candidates if candidate.strip()]
        if not candidates:
            return False
        for candidate in candidates:
            if any(candidate in identifier for identifier in identifiers):
                return True
        return False

    @staticmethod
    def check(
        name: str,
        passed: bool,
        severity: str,
        message: str = "",
        partial: float | None = None,
    ) -> dict[str, Any]:
        score = 1.0 if passed else 0.0
        if not passed and partial is not None:
            score = max(0.0, min(1.0, partial))
        return {
            "name": name,
            "passed": passed,
            "severity": severity,
            "score": round(score, 4),
            "message": message,
        }

    @staticmethod
    def layer(layer_name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
        score = sum(float(check["score"]) for check in checks) / max(1, len(checks))
        return {
            "layer": layer_name,
            "score": round(score, 4),
            "passed": all(check["passed"] for check in checks if check["severity"] in {"critical", "high"}),
            "checks": checks,
        }

    @staticmethod
    def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def write_summary_csv(layer_results: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["layer", "score", "passed", "check_count"])
            writer.writeheader()
            for row in layer_results:
                writer.writerow(
                    {
                        "layer": row["layer"],
                        "score": row["score"],
                        "passed": str(row["passed"]).lower(),
                        "check_count": len(row["checks"]),
                    }
                )

    @staticmethod
    def render_report(payload: dict[str, Any], failures: list[dict[str, Any]]) -> str:
        lines = [
            "# Artifact Benchmark Report",
            "",
            "## Decision",
            "",
            f"- passed: {str(payload['passed']).lower()}",
            f"- overall_score: {payload['overall_score']}",
            f"- pass_threshold: {payload['pass_threshold']}",
            f"- has_ground_truth_spec: {str(payload['has_ground_truth_spec']).lower()}",
            f"- failure_count: {payload['failure_count']}",
            "",
            "## Layer Scores",
            "",
        ]
        for result in payload["layer_results"]:
            lines.append(f"- {result['layer']}: score={result['score']} passed={str(result['passed']).lower()}")
        lines.extend(["", "## Failures", ""])
        if failures:
            for item in failures:
                lines.append(f"- [{item['severity']}] {item['layer']} / {item['check']}: {item['message']}")
        else:
            lines.append("- None.")
        lines.extend(["", "## Notes", ""])
        for note in payload["notes"]:
            lines.append(f"- {note}")
        return "\n".join(lines) + "\n"
