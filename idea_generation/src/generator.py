from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class IdeaGenerationResult:
    idea_candidates_md: str
    idea_candidates_json: str
    idea_count: int
    evidence_reference_count: int


class IdeaGenerator:
    """Generate conservative research idea candidates from current-run evidence.

    Ideas are proposals only. This module never claims novelty, SOTA status, or
    expected experimental performance.
    """

    def generate_ideas(self, task_input: dict[str, Any], output_dir: Path | str) -> IdeaGenerationResult:
        output_path = Path(output_dir)
        summary_path = Path(str(task_input.get("synthesis_summary_json") or output_path / "synthesis_summary.json"))
        evidence_path = Path(str(task_input.get("evidence_store_jsonl") or output_path / "evidence_store.jsonl"))
        if not summary_path.exists():
            raise FileNotFoundError(f"synthesis_summary.json not found: {summary_path}")
        if not evidence_path.exists():
            raise FileNotFoundError(f"evidence_store.jsonl not found: {evidence_path}")

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        evidence = self.read_jsonl(evidence_path)
        max_ideas = int(task_input.get("max_ideas", 5) or 5)
        ideas = self.build_ideas(summary=summary, evidence=evidence, max_ideas=max_ideas)

        payload = {
            "schema_version": "0.1",
            "idea_count": len(ideas),
            "ideas": ideas,
            "anti_hallucination_notes": [
                "Ideas are hypotheses for future work, not verified contributions.",
                "Evidence IDs identify motivation sources only; they do not prove novelty.",
                "Missing evidence is represented as a current-run gap, not a field-wide conclusion.",
            ],
        }
        json_path = output_path / "idea_candidates.json"
        md_path = output_path / "idea_candidates.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(self.render_markdown(payload), encoding="utf-8")
        evidence_refs = {
            evidence_id
            for idea in ideas
            for evidence_id in idea.get("supporting_evidence_ids", [])
            if evidence_id
        }
        return IdeaGenerationResult(
            idea_candidates_md=str(md_path),
            idea_candidates_json=str(json_path),
            idea_count=len(ideas),
            evidence_reference_count=len(evidence_refs),
        )

    @staticmethod
    def read_jsonl(path: Path) -> list[dict[str, Any]]:
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
    def build_ideas(summary: dict[str, Any], evidence: list[dict[str, Any]], max_ideas: int) -> list[dict[str, Any]]:
        evidence_ids = [str(item.get("evidence_id") or "") for item in evidence if item.get("evidence_id")]
        first_refs = evidence_ids[:3]
        gap_candidates = summary.get("research_gap_candidates")
        if not isinstance(gap_candidates, list):
            gap_candidates = []
        method_taxonomy = summary.get("method_taxonomy")
        if not isinstance(method_taxonomy, list):
            method_taxonomy = []
        metric_hints = summary.get("experiment_metric_hints")
        if not isinstance(metric_hints, list):
            metric_hints = []

        ideas: list[dict[str, Any]] = []
        for index, gap in enumerate(gap_candidates[:max_ideas], start=1):
            ideas.append(
                {
                    "idea_id": f"idea_{index}",
                    "title": f"Candidate study driven by current evidence gap {index}",
                    "type": "hypothesis",
                    "motivation": str(gap),
                    "proposed_direction": "Collect full-text evidence, define baselines, and test whether the gap remains after verification.",
                    "supporting_evidence_ids": first_refs,
                    "required_validation": [
                        "Search additional sources before claiming novelty.",
                        "Verify all source sections and benchmark settings.",
                        "Run ablations only after method and dataset details are fixed.",
                    ],
                    "risk_level": "high" if not first_refs else "medium",
                    "claim_status": "proposal_not_verified",
                }
            )

        if len(ideas) < max_ideas and method_taxonomy:
            refs = []
            for row in method_taxonomy:
                if isinstance(row, dict):
                    refs.extend(str(item) for item in row.get("evidence_ids", []) if item)
            ideas.append(
                {
                    "idea_id": f"idea_{len(ideas) + 1}",
                    "title": "Evidence-backed method taxonomy extension candidate",
                    "type": "design_probe",
                    "motivation": "Current synthesis contains method categories that can be compared under a shared schema.",
                    "proposed_direction": "Design a controlled comparison or hybridization only after confirming source methods from full text.",
                    "supporting_evidence_ids": refs[:5] or first_refs,
                    "required_validation": [
                        "Confirm taxonomy categories from original paper sections.",
                        "Construct fair baselines from verified implementations.",
                    ],
                    "risk_level": "medium",
                    "claim_status": "proposal_not_verified",
                }
            )

        if len(ideas) < max_ideas and metric_hints:
            refs = [str(row.get("evidence_id")) for row in metric_hints if isinstance(row, dict) and row.get("evidence_id")]
            ideas.append(
                {
                    "idea_id": f"idea_{len(ideas) + 1}",
                    "title": "Metric-grounded evaluation refinement candidate",
                    "type": "evaluation_probe",
                    "motivation": "Current evidence includes metric or benchmark hints that can shape an evaluation plan.",
                    "proposed_direction": "Turn extracted metric hints into a reproducible benchmark matrix before proposing claims.",
                    "supporting_evidence_ids": refs[:5] or first_refs,
                    "required_validation": [
                        "Validate numeric values against tables or source text.",
                        "Separate reported results from planned experiments.",
                    ],
                    "risk_level": "medium",
                    "claim_status": "proposal_not_verified",
                }
            )

        if not ideas:
            ideas.append(
                {
                    "idea_id": "idea_1",
                    "title": "Evidence collection before idea generation",
                    "type": "evidence_gap",
                    "motivation": "Current run does not contain enough verified evidence for responsible idea generation.",
                    "proposed_direction": "Retrieve and read more full-text sources before generating research claims.",
                    "supporting_evidence_ids": first_refs,
                    "required_validation": ["Add full-text papers.", "Re-run evidence extraction and synthesis."],
                    "risk_level": "high",
                    "claim_status": "insufficient_evidence",
                }
            )
        return ideas[:max_ideas]

    @staticmethod
    def render_markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# Idea Candidates",
            "",
            f"- idea_count: {payload['idea_count']}",
            "- status: proposal-only",
            "",
        ]
        for idea in payload["ideas"]:
            lines.extend(
                [
                    f"## {idea['idea_id']}: {idea['title']}",
                    "",
                    f"- type: {idea['type']}",
                    f"- risk_level: {idea['risk_level']}",
                    f"- claim_status: {idea['claim_status']}",
                    f"- motivation: {idea['motivation']}",
                    f"- proposed_direction: {idea['proposed_direction']}",
                    f"- supporting_evidence_ids: {', '.join(idea['supporting_evidence_ids']) or 'none'}",
                    "",
                    "Validation required:",
                    "",
                ]
            )
            for item in idea["required_validation"]:
                lines.append(f"- {item}")
            lines.append("")
        lines.extend(["## Notes", ""])
        for note in payload["anti_hallucination_notes"]:
            lines.append(f"- {note}")
        return "\n".join(lines) + "\n"
