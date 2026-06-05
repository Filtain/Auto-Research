from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class SearchQuery:
    query: str
    language: str
    source_targets: list[str]
    purpose: str


@dataclass
class PlannerResult:
    queries: list[SearchQuery]
    inclusion_criteria: list[str]
    exclusion_criteria: list[str]
    output_path: str


class Planner:
    """Deterministic planning module for early Auto Research runs."""

    def generate_search_queries(self, task_input: dict[str, Any], output_dir: Path | str) -> PlannerResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        topic = str(task_input.get("topic", "")).strip()
        questions = task_input.get("research_questions", [])
        depth = str(task_input.get("depth", "medium"))
        topic_terms = self.extract_core_terms(topic)

        queries = [
            SearchQuery(
                query=topic,
                language=self.detect_language(topic),
                source_targets=["arxiv"],
                purpose="primary_topic",
            )
        ]
        if topic_terms:
            queries.append(
                SearchQuery(
                    query=" ".join(topic_terms[:6]),
                    language="en",
                    source_targets=["arxiv"],
                    purpose="keyword_search",
                )
            )
        if isinstance(questions, list) and depth in {"medium", "detailed"}:
            for question in questions[:2]:
                question_text = str(question).strip()
                if question_text:
                    queries.append(
                        SearchQuery(
                            query=question_text,
                            language=self.detect_language(question_text),
                            source_targets=["arxiv"],
                            purpose="research_question",
                        )
                    )

        deduped_queries = self.deduplicate_queries(queries)
        result_path = output_path / "search_queries.json"
        payload = {
            "queries": [asdict(query) for query in deduped_queries],
            "inclusion_criteria": [
                "Topic or method is directly relevant to the research goal.",
                "Metadata is retrieved from a real source.",
                "Title and URL are present.",
            ],
            "exclusion_criteria": [
                "No clear relation to the research topic.",
                "Missing title or source URL.",
                "Duplicate metadata record.",
            ],
        }
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return PlannerResult(
            queries=deduped_queries,
            inclusion_criteria=payload["inclusion_criteria"],
            exclusion_criteria=payload["exclusion_criteria"],
            output_path=str(result_path),
        )

    @staticmethod
    def extract_core_terms(topic: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]+", topic)
        stopwords = {"and", "the", "for", "with", "from", "what", "how", "does"}
        return [token for token in tokens if token.lower() not in stopwords]

    @staticmethod
    def detect_language(text: str) -> str:
        return "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"

    @staticmethod
    def deduplicate_queries(queries: list[SearchQuery]) -> list[SearchQuery]:
        seen: set[str] = set()
        result: list[SearchQuery] = []
        for query in queries:
            key = query.query.strip().lower()
            if not key or key in seen:
                continue
            result.append(query)
            seen.add(key)
        return result
