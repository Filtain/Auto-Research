from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FinalQAResult:
    final_qa_report_md: str
    final_qa_result_json: str
    export_allowed: bool
    publication_ready: bool
    blocker_count: int
    warning_count: int
    checked_artifact_count: int


class FinalQAGate:
    """Final quality gate before export.

    This gate summarizes whether the current run can be exported as a verified
    artifact. It keeps a strict distinction between "workflow completed" and
    "safe to publish/export".
    """

    REQUIRED_ARTIFACTS = [
        "report.md",
        "source_map.json",
        "evidence_store.jsonl",
        "synthesis_summary.json",
        "verification_report.md",
        "verification_result.json",
        "claim_verification.jsonl",
        "unsupported_claims.jsonl",
        "citation_checks.jsonl",
        "citation_authority_checks.jsonl",
        "citation_graph_checks.jsonl",
        "numeric_table_checks.jsonl",
        "contradiction_checks.jsonl",
    ]

    def run_final_qa(self, task_input: dict[str, Any], output_dir: Path | str) -> FinalQAResult:
        output_path = Path(output_dir)
        required_artifacts = task_input.get("required_artifacts") or self.REQUIRED_ARTIFACTS
        if not isinstance(required_artifacts, list):
            required_artifacts = self.REQUIRED_ARTIFACTS

        verification_path = Path(str(task_input.get("verification_result_json") or output_path / "verification_result.json"))
        if not verification_path.exists():
            raise FileNotFoundError(f"verification_result.json not found: {verification_path}")
        verification = json.loads(verification_path.read_text(encoding="utf-8"))

        blockers: list[str] = []
        warnings: list[str] = []
        artifact_checks: list[dict[str, Any]] = []

        for artifact_name in required_artifacts:
            artifact_path = output_path / str(artifact_name)
            exists = artifact_path.exists()
            artifact_checks.append(
                {
                    "name": str(artifact_name),
                    "path": str(artifact_path),
                    "exists": exists,
                    "size_bytes": artifact_path.stat().st_size if exists else 0,
                }
            )
            if not exists:
                blockers.append(f"Missing required artifact: {artifact_name}")
            elif artifact_path.stat().st_size == 0:
                blockers.append(f"Required artifact is empty: {artifact_name}")

        if not bool(verification.get("verification_passed")):
            blockers.append("Verification did not pass.")
        if int(verification.get("unsupported_claim_count", 0)) > 0:
            blockers.append("Unsupported claims remain.")
        if int(verification.get("missing_evidence_count", 0)) > 0:
            blockers.append("Missing evidence references remain.")
        if not bool(verification.get("publication_ready")):
            blockers.append("Verification result is not publication-ready.")
        if int(verification.get("abstract_only_warning_count", 0)) > 0:
            warnings.append("Some claims rely on abstract/metadata-only evidence.")

        export_allowed = not blockers
        publication_ready = export_allowed and bool(verification.get("publication_ready"))
        result_payload = {
            "schema_version": "0.1",
            "export_allowed": export_allowed,
            "publication_ready": publication_ready,
            "blockers": blockers,
            "warnings": warnings,
            "artifact_checks": artifact_checks,
            "verification_summary": {
                "verification_passed": bool(verification.get("verification_passed")),
                "publication_ready": bool(verification.get("publication_ready")),
                "checked_claim_count": int(verification.get("checked_claim_count", 0)),
                "unsupported_claim_count": int(verification.get("unsupported_claim_count", 0)),
                "missing_evidence_count": int(verification.get("missing_evidence_count", 0)),
                "abstract_only_warning_count": int(verification.get("abstract_only_warning_count", 0)),
            },
            "notes": [
                "Final QA checks artifact completeness and verification gate results.",
                "A completed final QA task can still deny export.",
                "Abstract-only evidence blocks publication-ready export in this MVP.",
            ],
        }

        result_path = output_path / "final_qa_result.json"
        report_path = output_path / "final_qa_report.md"
        result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_path.write_text(self.render_report(result_payload), encoding="utf-8")

        return FinalQAResult(
            final_qa_report_md=str(report_path),
            final_qa_result_json=str(result_path),
            export_allowed=export_allowed,
            publication_ready=publication_ready,
            blocker_count=len(blockers),
            warning_count=len(warnings),
            checked_artifact_count=len(artifact_checks),
        )

    @staticmethod
    def render_report(result: dict[str, Any]) -> str:
        lines = [
            "# Final QA Report",
            "",
            "## Decision",
            "",
            f"- export_allowed: {str(result['export_allowed']).lower()}",
            f"- publication_ready: {str(result['publication_ready']).lower()}",
            f"- blocker_count: {len(result['blockers'])}",
            f"- warning_count: {len(result['warnings'])}",
            "",
            "## Blockers",
            "",
        ]
        if result["blockers"]:
            for blocker in result["blockers"]:
                lines.append(f"- {blocker}")
        else:
            lines.append("- None.")

        lines.extend(["", "## Warnings", ""])
        if result["warnings"]:
            for warning in result["warnings"]:
                lines.append(f"- {warning}")
        else:
            lines.append("- None.")

        lines.extend(["", "## Artifact Checks", ""])
        for artifact in result["artifact_checks"]:
            lines.append(
                f"- `{artifact['name']}`: exists={str(artifact['exists']).lower()} size={artifact['size_bytes']}"
            )

        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                "- Export is allowed only when all required artifacts exist and verification is publication-ready.",
                "- If abstract-only evidence remains, export is blocked until full-text evidence is added or policy changes.",
            ]
        )
        return "\n".join(lines) + "\n"
