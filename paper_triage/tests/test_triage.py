import csv
import tempfile
import unittest
from pathlib import Path

from paper_triage.src.triage import PaperTriage


class PaperTriageTests(unittest.TestCase):
    def test_rank_sources_outputs_ranked_csv_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_csv = Path(tmpdir) / "papers.csv"
            with papers_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
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
                        "retrieved_at",
                        "query",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "paper_id": "p1",
                        "title": "BANF band-limited neural fields for NeRF LOD",
                        "authors": "A",
                        "year": "2026",
                        "venue": "arXiv",
                        "doi": "",
                        "arxiv_id": "1",
                        "url": "https://arxiv.org/abs/1",
                        "abstract": "Neural fields and level of detail reconstruction.",
                        "citation_count": "",
                        "source": "arxiv",
                        "retrieved_at": "",
                        "query": "BANF NeRF",
                    }
                )
                writer.writerow(
                    {
                        "paper_id": "p2",
                        "title": "Unrelated robotics system",
                        "authors": "B",
                        "year": "2010",
                        "venue": "arXiv",
                        "doi": "",
                        "arxiv_id": "2",
                        "url": "https://arxiv.org/abs/2",
                        "abstract": "A robot paper.",
                        "citation_count": "",
                        "source": "arxiv",
                        "retrieved_at": "",
                        "query": "BANF NeRF",
                    }
                )

            result = PaperTriage().rank_sources(
                {"topic": "BANF band-limited neural fields NeRF LOD", "papers_csv": str(papers_csv)},
                tmpdir,
            )

            self.assertEqual(result.paper_count, 2)
            self.assertTrue(Path(result.ranked_papers_csv).exists())
            self.assertTrue(Path(result.triage_report_md).exists())
            with Path(result.ranked_papers_csv).open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["paper_id"], "p1")
            self.assertEqual(rows[0]["decision"], "include")

    def test_missing_papers_csv_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                PaperTriage().rank_sources({"papers_csv": str(Path(tmpdir) / "missing.csv")}, tmpdir)


if __name__ == "__main__":
    unittest.main()
