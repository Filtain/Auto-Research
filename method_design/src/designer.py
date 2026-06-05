from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MethodDesignResult:
    method_spec_md: str
    method_spec_json: str
    ablation_plan_md: str
    component_count: int
    ablation_count: int


class MethodDesigner:
    """Create a proposed method spec without claiming it has been validated."""

    def design_method(self, task_input: dict[str, Any], output_dir: Path | str) -> MethodDesignResult:
        output_path = Path(output_dir)
        ideas_path = Path(str(task_input.get("idea_candidates_json") or output_path / "idea_candidates.json"))
        literature_path = Path(str(task_input.get("literature_matrix_csv") or output_path / "literature_matrix.csv"))
        ideas = self.read_json(ideas_path).get("ideas", []) if ideas_path.exists() else []
        literature = self.read_csv(literature_path) if literature_path.exists() else []

        selected_idea = ideas[0] if ideas and isinstance(ideas[0], dict) else {}
        components = self.components(selected_idea=selected_idea, literature=literature)
        ablations = self.ablation_plan(components)
        payload = {
            "schema_version": "0.1",
            "status": "proposed_method_not_validated",
            "selected_idea_id": str(selected_idea.get("idea_id") or ""),
            "selected_idea_title": str(selected_idea.get("title") or ""),
            "problem_statement": str(selected_idea.get("motivation") or "Insufficient verified idea evidence."),
            "method_overview": "A conservative method design scaffold derived from current evidence artifacts.",
            "components": components,
            "inputs": ["verified source descriptions", "baseline list", "dataset specification"],
            "outputs": ["planned model outputs or evaluation artifacts; no results are claimed"],
            "training_or_execution_plan": [
                "Define baseline and data protocol from verified sources.",
                "Implement the smallest testable method variant.",
                "Run ablations before writing any performance claim.",
            ],
            "risks": [
                "Method details may be underspecified if full text is missing.",
                "Literature matrix cells are evidence-backed hints, not complete field coverage.",
            ],
        }

        spec_json = output_path / "method_spec.json"
        spec_md = output_path / "method_spec.md"
        ablation_md = output_path / "ablation_plan.md"
        spec_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        spec_md.write_text(self.render_spec(payload), encoding="utf-8")
        ablation_md.write_text(self.render_ablations(ablations), encoding="utf-8")
        return MethodDesignResult(
            method_spec_md=str(spec_md),
            method_spec_json=str(spec_json),
            ablation_plan_md=str(ablation_md),
            component_count=len(components),
            ablation_count=len(ablations),
        )

    @staticmethod
    def read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}

    @staticmethod
    def read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    @staticmethod
    def components(selected_idea: dict[str, Any], literature: list[dict[str, str]]) -> list[dict[str, Any]]:
        evidence_ids = selected_idea.get("supporting_evidence_ids")
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        if not evidence_ids:
            for row in literature[:3]:
                evidence_ids.extend(
                    item.strip() for item in str(row.get("evidence_ids", "")).split(";") if item.strip()
                )
        return [
            {
                "name": "evidence_grounded_problem_definition",
                "purpose": "Keep the method scoped to claims already present in evidence artifacts.",
                "evidence_ids": evidence_ids[:5],
                "status": "needs_source_confirmation",
            },
            {
                "name": "baseline_and_dataset_protocol",
                "purpose": "Define fair comparison settings before implementation.",
                "evidence_ids": evidence_ids[:5],
                "status": "planned",
            },
            {
                "name": "minimal_method_variant",
                "purpose": "Implement the smallest variant that can test the selected idea.",
                "evidence_ids": evidence_ids[:5],
                "status": "planned",
            },
        ]

    @staticmethod
    def ablation_plan(components: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [
            {
                "ablation_id": f"abl_{index}",
                "component": str(component["name"]),
                "question": f"Does `{component['name']}` change the verified evaluation target?",
                "metric_policy": "Use metrics only after source validation; do not invent values.",
                "status": "planned",
            }
            for index, component in enumerate(components, start=1)
        ]

    @staticmethod
    def render_spec(payload: dict[str, Any]) -> str:
        lines = [
            "# Method Specification",
            "",
            f"- status: {payload['status']}",
            f"- selected_idea_id: {payload['selected_idea_id'] or 'none'}",
            f"- selected_idea_title: {payload['selected_idea_title'] or 'none'}",
            "",
            "## Problem Statement",
            "",
            payload["problem_statement"],
            "",
            "## Components",
            "",
        ]
        for component in payload["components"]:
            lines.append(f"- `{component['name']}`: {component['purpose']} status={component['status']}")
        lines.extend(["", "## Risks", ""])
        for risk in payload["risks"]:
            lines.append(f"- {risk}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def render_ablations(ablations: list[dict[str, str]]) -> str:
        lines = ["# Ablation Plan", "", "- status: planned-only", ""]
        for item in ablations:
            lines.extend(
                [
                    f"## {item['ablation_id']}: {item['component']}",
                    "",
                    f"- question: {item['question']}",
                    f"- metric_policy: {item['metric_policy']}",
                    f"- status: {item['status']}",
                    "",
                ]
            )
        return "\n".join(lines)
