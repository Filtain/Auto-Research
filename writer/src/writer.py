from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm.src.provider import LLMClient


@dataclass
class WriterResult:
    final_report_md: str
    section_count: int
    llm_call_log_jsonl: str


class ResearchWriter:
    """Compose final user-facing report from verified artifacts."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def draft_paper(self, task_input: dict[str, Any], output_dir: Path | str) -> WriterResult:
        output_path = Path(output_dir)
        report = self.read_text(output_path / "report.md")
        verification = self.read_text(output_path / "verification_report.md")
        final_qa = self.read_text(output_path / "final_qa_report.md")
        comparison = self.read_text(output_path / "comparison_report.md")
        experiment = self.read_text(output_path / "experiment_plan.md")
        llm_summary = ""
        if bool(task_input.get("use_llm")):
            llm_client = self.llm_client
            if task_input.get("llm_provider") or task_input.get("llm_model"):
                llm_client = LLMClient(
                    provider=str(task_input.get("llm_provider") or "deterministic"),
                    model=str(task_input.get("llm_model") or "none"),
                )
            prompt = self.build_llm_prompt(
                report=report,
                comparison=comparison,
                experiment=experiment,
                verification=verification,
                final_qa=final_qa,
            )
            llm_result = llm_client.complete(prompt=prompt, output_dir=output_path)
            llm_summary = llm_result.text.strip()
        sections = [
            ("LLM-Assisted Executive Summary", llm_summary),
            ("Synthesis", report),
            ("Comparison", comparison),
            ("Experiment Plan", experiment),
            ("Verification", verification),
            ("Final QA", final_qa),
        ]
        lines = ["# Auto Research Final Report", ""]
        count = 0
        for title, body in sections:
            if not body.strip():
                continue
            count += 1
            lines.extend([f"## {title}", "", body.strip(), ""])
        lines.extend(
            [
                "## Use Notes",
                "",
                "- Claims should remain tied to evidence IDs.",
                "- LLM-assisted text is optional and must not be treated as new evidence.",
                "- If Final QA blocks export, treat this report as a draft only.",
            ]
        )
        output = output_path / "final_report.md"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return WriterResult(
            final_report_md=str(output),
            section_count=count,
            llm_call_log_jsonl=str(output_path / "llm_calls.jsonl"),
        )

    @staticmethod
    def read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @staticmethod
    def build_llm_prompt(
        report: str,
        comparison: str,
        experiment: str,
        verification: str,
        final_qa: str,
    ) -> str:
        return "\n\n".join(
            [
                "Write a concise executive summary for an Auto Research report.",
                "Do not introduce new citations, facts, metrics, claims, or conclusions.",
                "Only restate what is supported by the provided artifacts.",
                "If Final QA blocks export, explicitly state that the report is draft-only.",
                "[SYNTHESIS]\n" + report[:6000],
                "[COMPARISON]\n" + comparison[:3000],
                "[EXPERIMENT]\n" + experiment[:3000],
                "[VERIFICATION]\n" + verification[:3000],
                "[FINAL_QA]\n" + final_qa[:3000],
            ]
        )
