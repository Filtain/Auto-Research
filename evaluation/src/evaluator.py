from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvaluationResult:
    evaluation_report_md: str
    missing_experiments_md: str
    reviewer_risk_list_md: str
    risk_count: int
    missing_experiment_count: int


class ResearchEvaluator:
    """Evaluate evidence strength, QA status, and experiment completeness."""

    def evaluate_results(self, task_input: dict[str, Any], output_dir: Path | str) -> EvaluationResult:
        output_path = Path(output_dir)
        verification = self.read_json(output_path / "verification_result.json")
        final_qa = self.read_json(output_path / "final_qa_result.json")
        numeric = self.read_jsonl(output_path / "numeric_table_checks.jsonl")
        contradictions = self.read_jsonl(output_path / "contradiction_checks.jsonl")
        runs = self.read_jsonl(output_path / "experiment_runs.jsonl")

        risks = self.risks(verification, final_qa, numeric, contradictions, runs)
        missing = self.missing_experiments(runs=runs, verification=verification)
        eval_payload = {
            "verification_passed": bool(verification.get("verification_passed")),
            "publication_ready": bool(verification.get("publication_ready")),
            "final_qa_export_allowed": bool(final_qa.get("export_allowed")),
            "numeric_table_check_count": len(numeric),
            "contradiction_check_count": len(contradictions),
            "experiment_run_count": len(runs),
            "risk_count": len(risks),
            "missing_experiment_count": len(missing),
            "risks": risks,
            "missing_experiments": missing,
        }

        evaluation_path = output_path / "evaluation_report.md"
        missing_path = output_path / "missing_experiments.md"
        risk_path = output_path / "reviewer_risk_list.md"
        evaluation_path.write_text(self.render_evaluation(eval_payload), encoding="utf-8")
        missing_path.write_text(self.render_list("Missing Experiments", missing), encoding="utf-8")
        risk_path.write_text(self.render_list("Reviewer Risk List", risks), encoding="utf-8")
        return EvaluationResult(
            evaluation_report_md=str(evaluation_path),
            missing_experiments_md=str(missing_path),
            reviewer_risk_list_md=str(risk_path),
            risk_count=len(risks),
            missing_experiment_count=len(missing),
        )

    @staticmethod
    def read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
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
    def risks(
        verification: dict[str, Any],
        final_qa: dict[str, Any],
        numeric: list[dict[str, Any]],
        contradictions: list[dict[str, Any]],
        runs: list[dict[str, Any]],
    ) -> list[str]:
        risks: list[str] = []
        if not verification:
            risks.append("Verification result is missing; no export-quality evaluation is possible.")
        elif not verification.get("publication_ready"):
            risks.append("Verification is not publication-ready.")
        if final_qa and not final_qa.get("export_allowed"):
            risks.append("Final QA blocks export.")
        if any(item.get("status") in {"warning", "failed"} for item in numeric):
            risks.append("Numeric table validation contains warnings or failures.")
        if contradictions:
            risks.append("Contradiction candidates require manual review.")
        if not runs:
            risks.append("No experiment run logs are available; empirical claims must remain absent.")
        return risks

    @staticmethod
    def missing_experiments(runs: list[dict[str, Any]], verification: dict[str, Any]) -> list[str]:
        missing = []
        if not runs:
            missing.append("Run configured baseline and proposed-method experiments, or keep the artifact as plan-only.")
        if int(verification.get("abstract_only_warning_count", 0)) > 0:
            missing.append("Replace abstract-only evidence with full-text evidence before publication claims.")
        if int(verification.get("numeric_table_check_count", 0)) == 0:
            missing.append("Add source-grounded metric/table checks before quantitative comparison.")
        return missing

    @staticmethod
    def render_evaluation(payload: dict[str, Any]) -> str:
        lines = [
            "# Evaluation Report",
            "",
            f"- verification_passed: {str(payload['verification_passed']).lower()}",
            f"- publication_ready: {str(payload['publication_ready']).lower()}",
            f"- final_qa_export_allowed: {str(payload['final_qa_export_allowed']).lower()}",
            f"- experiment_run_count: {payload['experiment_run_count']}",
            f"- risk_count: {payload['risk_count']}",
            "",
            "## Interpretation",
            "",
            "- This report evaluates workflow readiness, not scientific truth.",
            "- Missing experiments mean claims must stay as plans or hypotheses.",
            "",
        ]
        lines.extend(["## Risks", ""])
        for risk in payload["risks"] or ["None detected by deterministic checks."]:
            lines.append(f"- {risk}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def render_list(title: str, rows: list[str]) -> str:
        lines = [f"# {title}", ""]
        for row in rows or ["None detected by deterministic checks."]:
            lines.append(f"- {row}")
        return "\n".join(lines) + "\n"
