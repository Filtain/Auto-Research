from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RebuttalResult:
    rebuttal_plan_md: str
    response_to_reviewers_md: str
    revision_checklist_md: str
    comment_count: int
    checklist_count: int


class RebuttalPlanner:
    """Draft a cautious rebuttal scaffold from actual reviewer comments."""

    def draft_rebuttal(self, task_input: dict[str, Any], output_dir: Path | str) -> RebuttalResult:
        output_path = Path(output_dir)
        comments = self.normalize_comments(task_input.get("reviewer_comments"))
        verification_text = self.read_text(output_path / "verification_report.md")
        evaluation_text = self.read_text(output_path / "evaluation_report.md")
        checklist = self.checklist(comments, verification_text, evaluation_text)

        plan_path = output_path / "rebuttal_plan.md"
        response_path = output_path / "response_to_reviewers.md"
        checklist_path = output_path / "revision_checklist.md"
        plan_path.write_text(self.render_plan(comments, checklist), encoding="utf-8")
        response_path.write_text(self.render_response(comments), encoding="utf-8")
        checklist_path.write_text(self.render_checklist(checklist), encoding="utf-8")
        return RebuttalResult(
            rebuttal_plan_md=str(plan_path),
            response_to_reviewers_md=str(response_path),
            revision_checklist_md=str(checklist_path),
            comment_count=len(comments),
            checklist_count=len(checklist),
        )

    @staticmethod
    def normalize_comments(value: Any) -> list[str]:
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @staticmethod
    def checklist(comments: list[str], verification_text: str, evaluation_text: str) -> list[str]:
        items = [
            "Map every response to a concrete manuscript or artifact change.",
            "Do not add new claims unless they are supported by verified evidence IDs.",
            "Separate completed revisions from planned future work.",
        ]
        if not comments:
            items.append("No reviewer comments were provided; collect comments before drafting point-by-point responses.")
        if "not publication-ready" in verification_text or "export_allowed: false" in evaluation_text:
            items.append("Resolve verification or Final QA blockers before making publication-ready claims.")
        return items

    @staticmethod
    def render_plan(comments: list[str], checklist: list[str]) -> str:
        lines = ["# Rebuttal Plan", "", f"- reviewer_comment_count: {len(comments)}", ""]
        if not comments:
            lines.append("No reviewer comments were provided. This file is a response scaffold only.")
            lines.append("")
        lines.extend(["## Checklist", ""])
        for item in checklist:
            lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def render_response(comments: list[str]) -> str:
        lines = ["# Response to Reviewers", ""]
        if not comments:
            lines.extend(
                [
                    "No reviewer comments were provided, so no substantive reviewer response has been generated.",
                    "",
                    "Use this scaffold only after real comments are available.",
                ]
            )
            return "\n".join(lines) + "\n"
        for index, comment in enumerate(comments, start=1):
            lines.extend(
                [
                    f"## Comment {index}",
                    "",
                    comment,
                    "",
                    "## Response",
                    "",
                    "Thank you for the comment. The response must be filled with evidence-backed changes only.",
                    "",
                    "## Planned Revision",
                    "",
                    "- Add the exact manuscript/artifact change here after verification.",
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def render_checklist(checklist: list[str]) -> str:
        lines = ["# Revision Checklist", ""]
        for item in checklist:
            lines.append(f"- [ ] {item}")
        return "\n".join(lines) + "\n"
