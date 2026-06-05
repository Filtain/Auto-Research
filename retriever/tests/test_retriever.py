import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retriever.src.retriever import PaperRecord, Retriever


class RetrieverTests(unittest.TestCase):
    def test_writes_papers_csv_with_header_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paper = PaperRecord(
                paper_id="arxiv:1234_5678",
                title="A Test Paper",
                authors=["Ada Lovelace", "Alan Turing"],
                year="2026",
                venue="arXiv",
                doi="",
                arxiv_id="1234.5678",
                url="https://arxiv.org/abs/1234.5678",
                abstract="A test abstract.",
                citation_count="",
                source="arxiv",
                retrieved_at="2026-05-25T00:00:00+00:00",
                query="test query",
            )

            Retriever.write_outputs(
                result=type("Result", (), {"papers": [paper], "errors": []})(),
                output_dir=Path(tmpdir),
            )

            csv_path = Path(tmpdir) / "papers.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["title"], "A Test Paper")
            self.assertEqual(rows[0]["authors"], "Ada Lovelace; Alan Turing")

    def test_unsupported_sources_are_logged_without_fabricating_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = Retriever().retrieve(
                query="BANF NeRF",
                output_dir=tmpdir,
                max_results=2,
                sources=["unsupported_source"],
            )

            self.assertEqual(result.papers, [])
            self.assertEqual(len(result.errors), 1)
            self.assertTrue((Path(tmpdir) / "papers.csv").exists())
            self.assertTrue((Path(tmpdir) / "retrieval_errors.jsonl").exists())

    @patch.object(Retriever, "search_arxiv")
    def test_retrieve_deduplicates_arxiv_results(self, mock_search_arxiv) -> None:
        paper = PaperRecord(
            paper_id="arxiv:1234_5678",
            title="Duplicate Paper",
            authors=["A"],
            year="2026",
            venue="arXiv",
            doi="",
            arxiv_id="1234.5678",
            url="https://arxiv.org/abs/1234.5678",
            abstract="",
            citation_count="",
            source="arxiv",
            retrieved_at="2026-05-25T00:00:00+00:00",
            query="duplicate",
        )
        mock_search_arxiv.return_value = [paper, paper]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = Retriever().retrieve(query="duplicate", output_dir=tmpdir, sources=["arxiv"])

        self.assertEqual(len(result.papers), 1)

    def test_local_pdf_source_creates_local_pdf_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "paper.pdf"
            pdf_path.write_text("We propose a local PDF method.", encoding="utf-8")

            result = Retriever().retrieve(
                query=str(pdf_path),
                output_dir=tmpdir,
                sources=["local_pdf"],
            )

            self.assertEqual(len(result.papers), 1)
            self.assertEqual(result.papers[0].source, "local_pdf")
            self.assertEqual(result.papers[0].local_pdf_path, str(pdf_path))

    @patch.object(Retriever, "read_json_url")
    def test_semantic_scholar_parser_normalizes_metadata(self, mock_read_json_url) -> None:
        mock_read_json_url.return_value = {
            "data": [
                {
                    "paperId": "abc",
                    "title": "Semantic Paper",
                    "authors": [{"name": "Ada"}],
                    "year": 2025,
                    "venue": "CVPR",
                    "abstract": "We propose a method.",
                    "citationCount": 7,
                    "externalIds": {"DOI": "10.1000/test", "ArXiv": "2501.12345"},
                    "url": "https://semanticscholar.org/paper/abc",
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                }
            ]
        }

        papers = Retriever().search_semantic_scholar("test", 1)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].source, "semantic_scholar")
        self.assertEqual(papers[0].doi, "10.1000/test")
        self.assertEqual(papers[0].pdf_url, "https://example.com/paper.pdf")

    @patch.object(Retriever, "read_json_url")
    def test_openalex_parser_reconstructs_abstract(self, mock_read_json_url) -> None:
        mock_read_json_url.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "OpenAlex Paper",
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1000/openalex",
                    "abstract_inverted_index": {"We": [0], "propose": [1]},
                    "authorships": [{"author": {"display_name": "Ada"}}],
                    "primary_location": {"pdf_url": "https://example.com/a.pdf", "source": {"display_name": "Venue"}},
                    "cited_by_count": 3,
                }
            ]
        }

        papers = Retriever().search_openalex("test", 1)

        self.assertEqual(papers[0].abstract, "We propose")
        self.assertEqual(papers[0].doi, "10.1000/openalex")


if __name__ == "__main__":
    unittest.main()
