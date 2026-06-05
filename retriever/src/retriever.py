from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PAPER_FIELDS = [
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
class PaperRecord:
    paper_id: str
    title: str
    authors: list[str]
    year: str
    venue: str
    doi: str
    arxiv_id: str
    url: str
    abstract: str
    citation_count: str
    source: str
    retrieved_at: str
    query: str
    pdf_url: str = ""
    local_pdf_path: str = ""


@dataclass
class RetrievalError:
    source: str
    query: str
    error: str


@dataclass
class RetrievalResult:
    papers: list[PaperRecord]
    errors: list[RetrievalError] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def stable_paper_id(source: str, identifier: str, title: str) -> str:
    raw = identifier or title
    cleaned = re.sub(r"[^\w]+", "_", raw.lower(), flags=re.UNICODE).strip("_")
    return f"{source}:{cleaned[:96] or 'unknown'}"


class Retriever:
    """Retrieve real paper metadata and write normalized artifacts.

    The implementation supports multiple metadata providers using Python's
    standard library. Network/API failures are recorded as retrieval errors
    rather than hidden or replaced with fabricated records.
    """

    SUPPORTED_SOURCES = {
        "arxiv",
        "semantic_scholar",
        "openalex",
        "crossref",
        "openreview",
        "pubmed",
        "github",
        "local_pdf",
    }

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def retrieve(
        self,
        query: str,
        output_dir: Path | str,
        max_results: int = 20,
        sources: list[str] | None = None,
    ) -> RetrievalResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        selected_sources = sources or ["arxiv"]

        papers: list[PaperRecord] = []
        errors: list[RetrievalError] = []
        for source in selected_sources:
            if source == "arxiv":
                try:
                    papers.extend(self.search_arxiv(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001 - write failure provenance for the user.
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "semantic_scholar":
                try:
                    papers.extend(self.search_semantic_scholar(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "openalex":
                try:
                    papers.extend(self.search_openalex(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "crossref":
                try:
                    papers.extend(self.search_crossref(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "openreview":
                try:
                    papers.extend(self.search_openreview(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "pubmed":
                try:
                    papers.extend(self.search_pubmed(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "github":
                try:
                    papers.extend(self.search_github(query=query, max_results=max_results))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            elif source == "local_pdf":
                try:
                    papers.extend(self.search_local_pdf(query=query))
                except Exception as exc:  # noqa: BLE001
                    errors.append(RetrievalError(source=source, query=query, error=str(exc)))
            else:
                errors.append(
                    RetrievalError(
                        source=source,
                        query=query,
                        error="Source is not supported by this retriever.",
                    )
                )

        deduped = self.deduplicate(papers)
        result = RetrievalResult(papers=deduped, errors=errors)
        self.write_outputs(result=result, output_dir=output_path)
        return result

    def search_arxiv(self, query: str, max_results: int) -> list[PaperRecord]:
        params = urllib.parse.urlencode(
            {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        url = f"https://export.arxiv.org/api/query?{params}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AutoResearchRetriever/0.1 (metadata retrieval)"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read()

        root = ET.fromstring(payload)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for entry in root.findall("atom:entry", ns):
            title = normalize_space(self._text(entry, "atom:title", ns))
            abstract = normalize_space(self._text(entry, "atom:summary", ns))
            authors = [
                normalize_space(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ]
            authors = [author for author in authors if author]
            entry_id = self._text(entry, "atom:id", ns)
            arxiv_id = entry_id.rstrip("/").split("/")[-1] if entry_id else ""
            published = self._text(entry, "atom:published", ns)
            year = published[:4] if published else ""
            doi = self._text(entry, "arxiv:doi", ns)
            url = entry_id

            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("arxiv", arxiv_id, title),
                    title=title,
                    authors=authors,
                    year=year,
                    venue="arXiv",
                    doi=doi,
                    arxiv_id=arxiv_id,
                    url=url,
                    abstract=abstract,
                    citation_count="",
                    source="arxiv",
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_semantic_scholar(self, query: str, max_results: int) -> list[PaperRecord]:
        fields = "title,authors,year,venue,abstract,citationCount,externalIds,url,openAccessPdf"
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search?"
            + urllib.parse.urlencode({"query": query, "limit": max_results, "fields": fields})
        )
        payload = self.read_json_url(url, user_agent="AutoResearchRetriever/0.1 (Semantic Scholar metadata)")
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for item in payload.get("data", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            external = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
            open_pdf = item.get("openAccessPdf") if isinstance(item.get("openAccessPdf"), dict) else {}
            title = normalize_space(str(item.get("title") or ""))
            paper_id = str(item.get("paperId") or "")
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("semantic_scholar", paper_id, title),
                    title=title,
                    authors=[
                        normalize_space(str(author.get("name") or ""))
                        for author in item.get("authors", [])
                        if isinstance(author, dict) and author.get("name")
                    ],
                    year=str(item.get("year") or ""),
                    venue=str(item.get("venue") or ""),
                    doi=str(external.get("DOI") or ""),
                    arxiv_id=str(external.get("ArXiv") or ""),
                    url=str(item.get("url") or ""),
                    abstract=normalize_space(str(item.get("abstract") or "")),
                    citation_count=str(item.get("citationCount") if item.get("citationCount") is not None else ""),
                    source="semantic_scholar",
                    pdf_url=str(open_pdf.get("url") or ""),
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_openalex(self, query: str, max_results: int) -> list[PaperRecord]:
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"search": query, "per-page": max_results}
        )
        payload = self.read_json_url(url, user_agent="AutoResearchRetriever/0.1 (OpenAlex metadata)")
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for item in payload.get("results", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            title = normalize_space(str(item.get("title") or item.get("display_name") or ""))
            authorships = item.get("authorships", [])
            authors = []
            for authorship in authorships:
                if isinstance(authorship, dict):
                    author = authorship.get("author")
                    if isinstance(author, dict) and author.get("display_name"):
                        authors.append(normalize_space(str(author["display_name"])))
            primary = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
            source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("openalex", str(item.get("id") or ""), title),
                    title=title,
                    authors=authors,
                    year=str(item.get("publication_year") or ""),
                    venue=str(source.get("display_name") or ""),
                    doi=str(item.get("doi") or "").removeprefix("https://doi.org/"),
                    arxiv_id="",
                    url=str(item.get("id") or ""),
                    abstract=self.openalex_abstract(item.get("abstract_inverted_index")),
                    citation_count=str(item.get("cited_by_count") if item.get("cited_by_count") is not None else ""),
                    source="openalex",
                    pdf_url=str(primary.get("pdf_url") or ""),
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_crossref(self, query: str, max_results: int) -> list[PaperRecord]:
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"query": query, "rows": max_results}
        )
        payload = self.read_json_url(url, user_agent="AutoResearchRetriever/0.1 (Crossref metadata)")
        message = payload.get("message") if isinstance(payload, dict) else {}
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for item in message.get("items", []) if isinstance(message, dict) else []:
            if not isinstance(item, dict):
                continue
            title = normalize_space(" ".join(item.get("title") or []))
            authors = [
                normalize_space(f"{author.get('given', '')} {author.get('family', '')}")
                for author in item.get("author", [])
                if isinstance(author, dict)
            ]
            year = self.crossref_year(item)
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("crossref", str(item.get("DOI") or ""), title),
                    title=title,
                    authors=[author for author in authors if author],
                    year=year,
                    venue=normalize_space(" ".join(item.get("container-title") or [])),
                    doi=str(item.get("DOI") or ""),
                    arxiv_id="",
                    url=str(item.get("URL") or ""),
                    abstract=normalize_space(self.strip_tags(str(item.get("abstract") or ""))),
                    citation_count=str(item.get("is-referenced-by-count") or ""),
                    source="crossref",
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_openreview(self, query: str, max_results: int) -> list[PaperRecord]:
        url = "https://api2.openreview.net/notes/search?" + urllib.parse.urlencode(
            {"term": query, "limit": max_results}
        )
        payload = self.read_json_url(url, user_agent="AutoResearchRetriever/0.1 (OpenReview metadata)")
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for item in payload.get("notes", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            title = str(content.get("title", {}).get("value") if isinstance(content.get("title"), dict) else content.get("title") or "")
            abstract = str(content.get("abstract", {}).get("value") if isinstance(content.get("abstract"), dict) else content.get("abstract") or "")
            authors_value = content.get("authors", {}).get("value") if isinstance(content.get("authors"), dict) else content.get("authors")
            authors = authors_value if isinstance(authors_value, list) else []
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("openreview", str(item.get("id") or ""), title),
                    title=normalize_space(title),
                    authors=[str(author) for author in authors],
                    year="",
                    venue="OpenReview",
                    doi="",
                    arxiv_id="",
                    url=f"https://openreview.net/forum?id={item.get('forum') or item.get('id') or ''}",
                    abstract=normalize_space(abstract),
                    citation_count="",
                    source="openreview",
                    pdf_url=f"https://openreview.net/pdf?id={item.get('forum') or item.get('id') or ''}",
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_pubmed(self, query: str, max_results: int) -> list[PaperRecord]:
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
        )
        search_payload = self.read_json_url(search_url, user_agent="AutoResearchRetriever/0.1 (PubMed metadata)")
        ids = search_payload.get("esearchresult", {}).get("idlist", []) if isinstance(search_payload, dict) else []
        if not ids:
            return []
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        )
        summary_payload = self.read_json_url(summary_url, user_agent="AutoResearchRetriever/0.1 (PubMed summary)")
        result = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for pubmed_id in ids:
            item = result.get(pubmed_id)
            if not isinstance(item, dict):
                continue
            title = normalize_space(str(item.get("title") or ""))
            authors = [
                normalize_space(str(author.get("name") or ""))
                for author in item.get("authors", [])
                if isinstance(author, dict) and author.get("name")
            ]
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("pubmed", pubmed_id, title),
                    title=title,
                    authors=authors,
                    year=str(item.get("pubdate") or "")[:4],
                    venue=str(item.get("source") or "PubMed"),
                    doi="",
                    arxiv_id="",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                    abstract="",
                    citation_count="",
                    source="pubmed",
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_github(self, query: str, max_results: int) -> list[PaperRecord]:
        url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
            {"q": query, "per_page": max_results}
        )
        payload = self.read_json_url(url, user_agent="AutoResearchRetriever/0.1 (GitHub repo search)")
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("full_name") or item.get("name") or "")
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("github", str(item.get("id") or ""), name),
                    title=name,
                    authors=[str(item.get("owner", {}).get("login") or "")] if isinstance(item.get("owner"), dict) else [],
                    year=str(item.get("created_at") or "")[:4],
                    venue="GitHub",
                    doi="",
                    arxiv_id="",
                    url=str(item.get("html_url") or ""),
                    abstract=normalize_space(str(item.get("description") or "")),
                    citation_count=str(item.get("stargazers_count") or ""),
                    source="github",
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    def search_local_pdf(self, query: str) -> list[PaperRecord]:
        pdf_paths = [part.strip() for part in query.split(",") if part.strip().lower().endswith(".pdf")]
        papers: list[PaperRecord] = []
        retrieved_at = utc_now()
        for raw_path in pdf_paths:
            path = Path(raw_path).expanduser()
            if not path.exists():
                continue
            title = path.stem.replace("_", " ")
            papers.append(
                PaperRecord(
                    paper_id=stable_paper_id("local_pdf", str(path), title),
                    title=title,
                    authors=[],
                    year="",
                    venue="Local PDF",
                    doi="",
                    arxiv_id="",
                    url=str(path),
                    abstract="",
                    citation_count="",
                    source="local_pdf",
                    local_pdf_path=str(path),
                    retrieved_at=retrieved_at,
                    query=query,
                )
            )
        return papers

    @staticmethod
    def deduplicate(papers: list[PaperRecord]) -> list[PaperRecord]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[PaperRecord] = []
        for paper in papers:
            key = (
                paper.doi.lower(),
                paper.arxiv_id.lower(),
                normalize_space(paper.title.lower()),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(paper)
        return deduped

    @staticmethod
    def write_outputs(result: RetrievalResult, output_dir: Path) -> None:
        Retriever.write_papers_csv(result.papers, output_dir / "papers.csv")
        Retriever.write_jsonl([asdict(paper) for paper in result.papers], output_dir / "papers_raw.jsonl")
        Retriever.write_jsonl(
            [
                {
                    "source": paper.source,
                    "query": paper.query,
                    "retrieved_at": paper.retrieved_at,
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "url": paper.url,
                    "pdf_url": paper.pdf_url,
                    "local_pdf_path": paper.local_pdf_path,
                }
                for paper in result.papers
            ],
            output_dir / "search_results.jsonl",
        )
        Retriever.write_jsonl([asdict(error) for error in result.errors], output_dir / "retrieval_errors.jsonl")

    @staticmethod
    def write_papers_csv(papers: list[PaperRecord], path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PAPER_FIELDS)
            writer.writeheader()
            for paper in papers:
                row = asdict(paper)
                row["authors"] = "; ".join(paper.authors)
                writer.writerow(row)

    @staticmethod
    def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _text(entry: ET.Element, path: str, ns: dict[str, str]) -> str:
        value = entry.findtext(path, default="", namespaces=ns)
        return value or ""

    def read_json_url(self, url: str, user_agent: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read()
        decoded = payload.decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def openalex_abstract(inverted_index: Any) -> str:
        if not isinstance(inverted_index, dict):
            return ""
        positions: dict[int, str] = {}
        for word, indexes in inverted_index.items():
            if not isinstance(indexes, list):
                continue
            for index in indexes:
                if isinstance(index, int):
                    positions[index] = str(word)
        return normalize_space(" ".join(positions[index] for index in sorted(positions)))

    @staticmethod
    def crossref_year(item: dict[str, Any]) -> str:
        for key in ["published-print", "published-online", "published", "created"]:
            date_parts = item.get(key, {}).get("date-parts") if isinstance(item.get(key), dict) else None
            if date_parts and isinstance(date_parts, list) and date_parts[0]:
                return str(date_parts[0][0])
        return ""

    @staticmethod
    def strip_tags(text: str) -> str:
        return re.sub(r"<[^>]+>", " ", text)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve paper metadata for Auto Research.")
    parser.add_argument("query", help="Search query.")
    parser.add_argument("--output-dir", required=True, help="Directory for papers.csv and JSONL outputs.")
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument(
        "--sources",
        default="arxiv",
        help="Comma-separated source list. MVP supports arxiv; unsupported sources are logged.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    result = Retriever().retrieve(
        query=args.query,
        output_dir=args.output_dir,
        max_results=args.max_results,
        sources=sources,
    )
    print(
        json.dumps(
            {
                "papers_csv": str(Path(args.output_dir) / "papers.csv"),
                "paper_count": len(result.papers),
                "error_count": len(result.errors),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
