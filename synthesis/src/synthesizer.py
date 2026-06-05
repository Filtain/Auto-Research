from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SynthesisResult:
    report_md: str
    synthesis_summary_json: str
    evidence_count: int
    paper_count: int
    claim_type_count: dict[str, int]
    abstract_only_evidence_count: int


class FindingsSynthesizer:
    """Generate a conservative synthesis from evidence records.

    The MVP intentionally avoids inventing research conclusions. It groups and
    restates evidence-backed claims, then labels coverage gaps as observations
    about the current evidence set rather than claims about the field.
    """

    def synthesize_findings(self, task_input: dict[str, Any], output_dir: Path | str) -> SynthesisResult:
        output_path = Path(output_dir)
        evidence_path = Path(str(task_input.get("evidence_store_jsonl") or output_path / "evidence_store.jsonl"))
        source_map_path = Path(str(task_input.get("source_map_json") or output_path / "source_map.json"))
        if not evidence_path.exists():
            raise FileNotFoundError(f"evidence_store.jsonl not found: {evidence_path}")
        if not source_map_path.exists():
            raise FileNotFoundError(f"source_map.json not found: {source_map_path}")

        evidence_items = self.read_jsonl(evidence_path)
        source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
        papers = source_map.get("papers") if isinstance(source_map, dict) else {}
        if not isinstance(papers, dict):
            papers = {}

        grouped_by_paper = self.group_by_paper(evidence_items)
        claim_type_count = Counter(str(item.get("claim_type") or "unknown") for item in evidence_items)
        abstract_only_count = sum(
            1 for item in evidence_items if item.get("support_level") == "abstract_metadata_only"
        )
        summary = {
            "schema_version": "0.1",
            "paper_count": len(papers) or len(grouped_by_paper),
            "evidence_count": len(evidence_items),
            "claim_type_count": dict(claim_type_count),
            "abstract_only_evidence_count": abstract_only_count,
            "full_text_evidence_count": sum(
                1 for item in evidence_items if item.get("support_level") == "full_text_evidence"
            ),
            "source_files": {
                "evidence_store_jsonl": str(evidence_path),
                "source_map_json": str(source_map_path),
            },
            "paper_evidence": self.paper_evidence_summary(grouped_by_paper),
            "timeline": self.timeline(papers, grouped_by_paper),
            "method_taxonomy": self.method_taxonomy(evidence_items),
            "experiment_metric_hints": self.experiment_metric_hints(evidence_items),
            "coverage_gaps": self.coverage_gaps(evidence_items),
            "research_gap_candidates": self.research_gap_candidates(evidence_items),
            "reproducibility_route": self.reproducibility_route(evidence_items),
            "anti_hallucination_notes": [
                "Synthesis statements are generated from evidence_store.jsonl only.",
                "Abstract-only evidence is labeled and must be verified before final publication use.",
                "Coverage gaps describe missing evidence in this run, not definitive gaps in the research field.",
            ],
        }

        report_path = output_path / "report.md"
        summary_path = output_path / "synthesis_summary.json"
        report_path.write_text(self.render_report(summary, grouped_by_paper), encoding="utf-8")
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return SynthesisResult(
            report_md=str(report_path),
            synthesis_summary_json=str(summary_path),
            evidence_count=len(evidence_items),
            paper_count=int(summary["paper_count"]),
            claim_type_count=dict(claim_type_count),
            abstract_only_evidence_count=abstract_only_count,
        )

    @staticmethod
    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if isinstance(record, dict):
                    records.append(record)
        return records

    @staticmethod
    def group_by_paper(evidence_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in evidence_items:
            paper_id = str(item.get("paper_id") or "unknown_paper")
            grouped[paper_id].append(item)
        return dict(grouped)

    @staticmethod
    def paper_evidence_summary(grouped_by_paper: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for paper_id, items in sorted(grouped_by_paper.items()):
            title = str(items[0].get("paper_title") or "")
            rows.append(
                {
                    "paper_id": paper_id,
                    "paper_title": title,
                    "evidence_count": len(items),
                    "evidence_ids": [str(item.get("evidence_id") or "") for item in items],
                    "claim_types": dict(Counter(str(item.get("claim_type") or "unknown") for item in items)),
                }
            )
        return rows

    @staticmethod
    def coverage_gaps(evidence_items: list[dict[str, Any]]) -> list[str]:
        gaps: list[str] = []
        if not evidence_items:
            return ["No evidence records were available for synthesis."]
        if all(item.get("support_level") == "abstract_metadata_only" for item in evidence_items):
            gaps.append("Current synthesis is based only on title/abstract metadata.")
        if not any(item.get("claim_type") == "finding" for item in evidence_items):
            gaps.append("No result/finding evidence was extracted in this run.")
        if not any(item.get("full_text_available") for item in evidence_items):
            gaps.append("No full-text evidence was available in this run.")
        return gaps

    @staticmethod
    def timeline(papers: dict[str, Any], grouped_by_paper: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for paper_id, items in grouped_by_paper.items():
            paper = papers.get(paper_id, {}) if isinstance(papers, dict) else {}
            bib = paper.get("bibliographic_info", {}) if isinstance(paper, dict) else {}
            if not isinstance(bib, dict):
                bib = {}
            rows.append(
                {
                    "year": str(bib.get("year") or ""),
                    "paper_id": paper_id,
                    "paper_title": str(items[0].get("paper_title") or ""),
                    "evidence_ids": "; ".join(str(item.get("evidence_id") or "") for item in items),
                }
            )
        return sorted(rows, key=lambda row: (row["year"] or "9999", row["paper_title"]))

    @staticmethod
    def method_taxonomy(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        categories = {
            "neural_field": ["neural field", "nerf", "radiance field"],
            "gaussian_splatting": ["gaussian", "splatting"],
            "acceleration": ["fast", "efficient", "instant", "hash", "real-time"],
            "level_of_detail": ["lod", "level of detail", "multi-resolution", "multiresolution"],
            "optimization": ["optimize", "training", "loss"],
        }
        rows: list[dict[str, Any]] = []
        for category, keywords in categories.items():
            matches = [
                item
                for item in evidence_items
                if any(keyword in str(item.get("claim", "")).lower() for keyword in keywords)
            ]
            if matches:
                rows.append(
                    {
                        "category": category,
                        "evidence_count": len(matches),
                        "evidence_ids": [str(item.get("evidence_id") or "") for item in matches],
                    }
                )
        return rows

    @staticmethod
    def experiment_metric_hints(evidence_items: list[dict[str, Any]]) -> list[dict[str, str]]:
        keywords = ["dataset", "benchmark", "psnr", "ssim", "lpips", "accuracy", "result", "outperform"]
        rows: list[dict[str, str]] = []
        for item in evidence_items:
            claim = str(item.get("claim") or "")
            if any(keyword in claim.lower() for keyword in keywords):
                rows.append(
                    {
                        "evidence_id": str(item.get("evidence_id") or ""),
                        "paper_id": str(item.get("paper_id") or ""),
                        "hint": claim,
                    }
                )
        return rows

    @staticmethod
    def research_gap_candidates(evidence_items: list[dict[str, Any]]) -> list[str]:
        return [f"Current-run gap candidate: {gap}" for gap in FindingsSynthesizer.coverage_gaps(evidence_items)]

    @staticmethod
    def reproducibility_route(evidence_items: list[dict[str, Any]]) -> list[str]:
        route = [
            "Inspect `source_map.json` for each evidence ID.",
            "Prioritize full-text/PDF evidence over abstract-only evidence.",
            "Use `literature_matrix.csv` and `benchmark_matrix.csv` when available.",
            "Create environment, data, metric, and baseline checklist before running experiments.",
        ]
        if any(
            "github" in str(item.get("claim", "")).lower() or "code" in str(item.get("claim", "")).lower()
            for item in evidence_items
        ):
            route.append("Follow extracted code availability evidence before searching unofficial repositories.")
        return route

    def render_report(self, summary: dict[str, Any], grouped_by_paper: dict[str, list[dict[str, Any]]]) -> str:
        lines = [
            "# Auto Research Synthesis Report",
            "",
            "## Scope",
            "",
            f"- papers_with_evidence: {summary['paper_count']}",
            f"- evidence_records: {summary['evidence_count']}",
            f"- abstract_only_evidence: {summary['abstract_only_evidence_count']}",
            "",
            "## Evidence-Grounded Claims",
            "",
        ]
        if not grouped_by_paper:
            lines.append("- No evidence records available.")
        for paper_id, items in sorted(grouped_by_paper.items()):
            title = str(items[0].get("paper_title") or "(missing title)")
            lines.append(f"### {title}")
            lines.append("")
            lines.append(f"- paper_id: `{paper_id}`")
            for item in items:
                evidence_id = str(item.get("evidence_id") or "")
                claim_type = str(item.get("claim_type") or "unknown")
                support_level = str(item.get("support_level") or "unknown")
                claim = str(item.get("claim") or "").strip()
                lines.append(f"- [{evidence_id}] ({claim_type}, {support_level}) {claim}")
            lines.append("")

        lines.extend(["## Timeline", ""])
        timeline = summary.get("timeline") or []
        if timeline:
            for row in timeline:
                year = row.get("year") or "unknown year"
                lines.append(f"- {year}: {row.get('paper_title') or row.get('paper_id')} [{row.get('evidence_ids')}]")
        else:
            lines.append("- No timeline entries available from current evidence.")

        lines.extend(["", "## Method Taxonomy", ""])
        taxonomy = summary.get("method_taxonomy") or []
        if taxonomy:
            for row in taxonomy:
                ids = ", ".join(row.get("evidence_ids") or [])
                lines.append(f"- {row.get('category')}: {row.get('evidence_count')} evidence records ({ids})")
        else:
            lines.append("- No method taxonomy categories were detected from current evidence.")

        lines.extend(["", "## Experiment Metric Hints", ""])
        metric_hints = summary.get("experiment_metric_hints") or []
        if metric_hints:
            for row in metric_hints:
                lines.append(f"- [{row.get('evidence_id')}] {row.get('hint')}")
        else:
            lines.append("- No dataset/metric/result hints were extracted from current evidence.")

        lines.append("")
        lines.extend(
            [
                "## Coverage Gaps",
                "",
            ]
        )
        gaps = summary.get("coverage_gaps") or []
        if gaps:
            for gap in gaps:
                lines.append(f"- {gap}")
        else:
            lines.append("- No coverage gaps detected by this MVP synthesizer.")

        lines.extend(["", "## Research Gap Candidates", ""])
        gap_candidates = summary.get("research_gap_candidates") or []
        if gap_candidates:
            for gap in gap_candidates:
                lines.append(f"- {gap}")
        else:
            lines.append("- No research gap candidates were generated from current-run coverage gaps.")

        lines.extend(
            [
                "",
                "## Reproducibility Route",
                "",
            ]
        )
        for step in summary.get("reproducibility_route") or []:
            lines.append(f"- {step}")
        lines.extend(
            [
                "",
                "## Anti-Hallucination Notes",
                "",
                "- This report does not introduce citations beyond the evidence store.",
                "- Statements above are copied or tightly restated from extracted evidence records.",
                "- Field-level research gaps are not asserted here; only current-run evidence coverage gaps are listed.",
            ]
        )
        return "\n".join(lines) + "\n"
