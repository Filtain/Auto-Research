from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


RANKED_FIELDS = [
    "rank",
    "decision",
    "score",
    "relevance_score",
    "recency_score",
    "metadata_score",
    "reason",
    "paper_id",
    "title",
    "authors",
    "year",
    "venue",
    "doi",
    "arxiv_id",
    "url",
    "abstract",
    "citation_count",
    "source",
    "pdf_url",
    "local_pdf_path",
    "retrieved_at",
    "query",
]


@dataclass
class TriageResult:
    ranked_papers_csv: str
    triage_report_md: str
    paper_count: int
    included_count: int
    maybe_count: int
    excluded_count: int


class PaperTriage:
    """Deterministic paper triage over retrieved metadata."""

    def rank_sources(self, task_input: dict[str, Any], output_dir: Path | str) -> TriageResult:
        output_path = Path(output_dir)
        papers_csv = Path(str(task_input.get("papers_csv") or output_path / "papers.csv"))
        if not papers_csv.exists():
            raise FileNotFoundError(f"papers.csv not found: {papers_csv}")

        topic = str(task_input.get("topic", "")).strip()
        criteria = task_input.get("criteria", [])
        if not isinstance(criteria, list):
            criteria = []

        papers = self.read_papers(papers_csv)
        ranked = [self.score_paper(row, topic=topic) for row in papers]
        ranked.sort(key=lambda row: (-float(row["score"]), self.safe_int(row.get("year")), row.get("title", "")))
        for index, row in enumerate(ranked, start=1):
            row["rank"] = str(index)
            row["decision"] = self.decision_for_score(float(row["score"]))

        ranked_path = output_path / "ranked_papers.csv"
        report_path = output_path / "triage_report.md"
        self.write_ranked_csv(ranked, ranked_path)
        self.write_report(ranked, report_path, topic=topic, criteria=criteria)

        return TriageResult(
            ranked_papers_csv=str(ranked_path),
            triage_report_md=str(report_path),
            paper_count=len(ranked),
            included_count=sum(1 for row in ranked if row["decision"] == "include"),
            maybe_count=sum(1 for row in ranked if row["decision"] == "maybe"),
            excluded_count=sum(1 for row in ranked if row["decision"] == "exclude"),
        )

    @staticmethod
    def read_papers(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def score_paper(self, row: dict[str, str], topic: str) -> dict[str, str]:
        title = row.get("title", "")
        abstract = row.get("abstract", "")
        relevance = self.relevance_score(topic=topic, title=title, abstract=abstract)
        recency = self.recency_score(row.get("year", ""))
        metadata = self.metadata_score(row)
        score = relevance * 0.6 + recency * 0.25 + metadata * 0.15
        reason = self.reason(relevance, recency, metadata)
        result = {field: row.get(field, "") for field in RANKED_FIELDS}
        result.update(
            {
                "score": f"{score:.3f}",
                "relevance_score": f"{relevance:.3f}",
                "recency_score": f"{recency:.3f}",
                "metadata_score": f"{metadata:.3f}",
                "reason": reason,
            }
        )
        return result

    @staticmethod
    def relevance_score(topic: str, title: str, abstract: str) -> float:
        terms = PaperTriage.tokenize(topic)
        if not terms:
            return 0.0
        text = f"{title} {abstract}".lower()
        matches = sum(1 for term in terms if term in text)
        return min(1.0, matches / max(1, len(terms)))

    @staticmethod
    def recency_score(year_value: str) -> float:
        year = PaperTriage.safe_int(year_value)
        if year <= 0:
            return 0.0
        current_year = datetime.now().year
        age = max(0, current_year - year)
        if age <= 2:
            return 1.0
        if age <= 5:
            return 0.75
        if age <= 10:
            return 0.45
        return 0.2

    @staticmethod
    def metadata_score(row: dict[str, str]) -> float:
        fields = ["title", "authors", "year", "url", "abstract", "source"]
        present = sum(1 for field in fields if row.get(field, "").strip())
        return present / len(fields)

    @staticmethod
    def tokenize(text: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]+", text.lower())
        stopwords = {
            "and",
            "the",
            "for",
            "with",
            "from",
            "what",
            "how",
            "does",
            "paper",
            "related",
        }
        return [token for token in dict.fromkeys(tokens) if token not in stopwords]

    @staticmethod
    def safe_int(value: str | None) -> int:
        try:
            return int(str(value or "").strip())
        except ValueError:
            return 0

    @staticmethod
    def decision_for_score(score: float) -> str:
        if score >= 0.65:
            return "include"
        if score >= 0.35:
            return "maybe"
        return "exclude"

    @staticmethod
    def reason(relevance: float, recency: float, metadata: float) -> str:
        parts = []
        if relevance >= 0.65:
            parts.append("high topic match")
        elif relevance >= 0.35:
            parts.append("partial topic match")
        else:
            parts.append("weak topic match")
        if recency >= 0.75:
            parts.append("recent")
        elif recency <= 0.2:
            parts.append("older or missing year")
        if metadata >= 0.85:
            parts.append("metadata mostly complete")
        elif metadata < 0.5:
            parts.append("metadata incomplete")
        return "; ".join(parts)

    @staticmethod
    def write_ranked_csv(rows: list[dict[str, str]], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RANKED_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def write_report(rows: list[dict[str, str]], path: Path, topic: str, criteria: list[str]) -> None:
        included = [row for row in rows if row["decision"] == "include"]
        maybe = [row for row in rows if row["decision"] == "maybe"]
        excluded = [row for row in rows if row["decision"] == "exclude"]

        lines = [
            "# Paper Triage Report",
            "",
            f"- topic: {topic or 'not provided'}",
            f"- total_papers: {len(rows)}",
            f"- include: {len(included)}",
            f"- maybe: {len(maybe)}",
            f"- exclude: {len(excluded)}",
            "",
            "## Criteria",
            "",
        ]
        if criteria:
            lines.extend(f"- {criterion}" for criterion in criteria)
        else:
            lines.append("- relevance, recency, metadata completeness")
        lines.extend(["", "## Top Ranked Papers", ""])
        for row in rows[:10]:
            title = row.get("title") or "(missing title)"
            lines.append(f"{row['rank']}. [{row['decision']}] {title} - score {row['score']}")
            lines.append(f"   reason: {row['reason']}")
        lines.extend(
            [
                "",
                "## Notes",
                "",
                "- Scores are deterministic triage heuristics, not scientific quality claims.",
                "- Missing metadata was not invented.",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
