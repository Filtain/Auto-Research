import csv
import json
import tempfile
import unittest
from pathlib import Path

from paper_reader.src.reader import PaperLayoutBlock, PaperReader


class PaperReaderTests(unittest.TestCase):
    def test_parse_table_candidate_outputs_structured_rows(self) -> None:
        parsed = PaperReader().parse_table_candidate(
            "\n".join(
                [
                    "Table 1 Results",
                    "Method  PSNR  SSIM",
                    "Baseline  28.0  0.85",
                    "DemoNF    31.0  0.91",
                ]
            )
        )

        self.assertEqual(parsed["headers"], ["Method", "PSNR", "SSIM"])
        self.assertEqual(parsed["rows"][1]["cells"]["Method"], "DemoNF")
        self.assertEqual(parsed["rows"][1]["numeric_cells"]["PSNR"], "31.0")
        self.assertEqual(parsed["numeric_cell_count"], 4)

    def test_read_core_sources_outputs_jsonl_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ranked_csv = Path(tmpdir) / "ranked_papers.csv"
            with ranked_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rank",
                        "decision",
                        "score",
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
                        "rank": "1",
                        "decision": "include",
                        "score": "0.9",
                        "paper_id": "p1",
                        "title": "BANF Neural Fields",
                        "authors": "A",
                        "year": "2026",
                        "venue": "arXiv",
                        "doi": "",
                        "arxiv_id": "1",
                        "url": "https://arxiv.org/abs/1",
                        "abstract": "We propose a neural field method. The code is available at https://example.com.",
                        "citation_count": "",
                        "source": "arxiv",
                        "retrieved_at": "",
                        "query": "BANF",
                    }
                )
                writer.writerow(
                    {
                        "rank": "2",
                        "decision": "exclude",
                        "score": "0.1",
                        "paper_id": "p2",
                        "title": "Excluded Paper",
                        "authors": "B",
                        "year": "2020",
                        "venue": "arXiv",
                        "doi": "",
                        "arxiv_id": "2",
                        "url": "https://arxiv.org/abs/2",
                        "abstract": "Irrelevant.",
                        "citation_count": "",
                        "source": "arxiv",
                        "retrieved_at": "",
                        "query": "BANF",
                    }
                )

            result = PaperReader().read_core_sources(
                {"ranked_papers_csv": str(ranked_csv), "max_papers": 5},
                tmpdir,
            )

            self.assertEqual(result.paper_count, 1)
            self.assertEqual(result.abstract_only_count, 1)
            self.assertTrue(Path(result.paper_readings_jsonl).exists())
            self.assertTrue(Path(result.paper_reading_report_md).exists())
            lines = Path(result.paper_readings_jsonl).read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            self.assertFalse(record["full_text_available"])
            self.assertEqual(record["read_source"], "abstract_metadata_only")
            self.assertEqual(record["paper_id"], "p1")
            self.assertGreaterEqual(len(record["claims"]), 1)

    def test_missing_ranked_csv_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                PaperReader().read_core_sources(
                    {"ranked_papers_csv": str(Path(tmpdir) / "missing.csv")},
                    tmpdir,
                )

    def test_local_pdf_full_text_is_used_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            pdf_path = output_dir / "paper.pdf"
            pdf_path.write_text("We propose a full text neural field method.", encoding="utf-8")
            ranked_csv = output_dir / "ranked_papers.csv"
            with ranked_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rank",
                        "decision",
                        "score",
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
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "rank": "1",
                        "decision": "include",
                        "score": "0.9",
                        "paper_id": "p1",
                        "title": "Full Text Paper",
                        "authors": "A",
                        "year": "2026",
                        "venue": "Local PDF",
                        "doi": "",
                        "arxiv_id": "",
                        "url": str(pdf_path),
                        "abstract": "",
                        "citation_count": "",
                        "source": "local_pdf",
                        "pdf_url": "",
                        "local_pdf_path": str(pdf_path),
                        "retrieved_at": "",
                        "query": str(pdf_path),
                    }
                )

            result = PaperReader().read_core_sources({"ranked_papers_csv": str(ranked_csv)}, output_dir)

            self.assertEqual(result.full_text_count, 1)
            record = json.loads(Path(result.paper_readings_jsonl).read_text(encoding="utf-8").splitlines()[0])
            self.assertTrue(record["full_text_available"])
            self.assertTrue(record["read_source"].startswith("pdf_full_text:"))
            self.assertTrue(Path(result.paper_fulltext_chunks_jsonl).exists())

    def test_full_text_extracts_sections_tables_and_formulas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            pdf_path = output_dir / "paper.pdf"
            pdf_path.write_text(
                "\n".join(
                    [
                        "Abstract",
                        "We propose a method for neural fields.",
                        "1 Introduction",
                        "This paper introduces the task.",
                        "2 Method",
                        "E = mc^2 (1)",
                        "3 Experiments",
                        "Table 1 Results",
                        "Method  PSNR  SSIM",
                        "Ours    31.0  0.91",
                    ]
                ),
                encoding="utf-8",
            )
            ranked_csv = output_dir / "ranked_papers.csv"
            with ranked_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "rank",
                        "decision",
                        "score",
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
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "rank": "1",
                        "decision": "include",
                        "score": "0.9",
                        "paper_id": "p1",
                        "title": "Structured PDF Paper",
                        "authors": "A",
                        "year": "2026",
                        "venue": "Local PDF",
                        "doi": "",
                        "arxiv_id": "",
                        "url": str(pdf_path),
                        "abstract": "",
                        "citation_count": "",
                        "source": "local_pdf",
                        "pdf_url": "",
                        "local_pdf_path": str(pdf_path),
                        "retrieved_at": "",
                        "query": str(pdf_path),
                    }
                )

            result = PaperReader().read_core_sources({"ranked_papers_csv": str(ranked_csv)}, output_dir)

            self.assertGreaterEqual(result.section_count, 3)
            self.assertGreaterEqual(result.table_count, 1)
            self.assertGreaterEqual(result.formula_count, 1)
            self.assertTrue(Path(result.paper_sections_jsonl).exists())
            self.assertTrue(Path(result.paper_tables_jsonl).exists())
            self.assertTrue(Path(result.paper_structured_tables_jsonl).exists())
            self.assertTrue(Path(result.paper_structured_tables_csv).exists())
            self.assertTrue(Path(result.paper_formulas_jsonl).exists())
            structured_tables = Path(result.paper_structured_tables_jsonl).read_text(encoding="utf-8")
            structured_cells = Path(result.paper_structured_tables_csv).read_text(encoding="utf-8")
            self.assertIn("PSNR", structured_tables)
            self.assertIn("31.0", structured_cells)

    def test_layout_blocks_drive_sections_tables_and_formulas_with_geometry(self) -> None:
        reader = PaperReader()
        blocks = [
            PaperLayoutBlock(
                block_id="page:1:block:1",
                page=1,
                block_type="text",
                text="Abstract",
                bbox=[72.0, 60.0, 160.0, 78.0],
                column=1,
                font_size=14.0,
                is_bold=True,
                line_count=1,
                confidence="high",
            ),
            PaperLayoutBlock(
                block_id="page:1:block:2",
                page=1,
                block_type="text",
                text="We propose a layout-aware neural field method.",
                bbox=[72.0, 90.0, 420.0, 110.0],
                column=1,
                font_size=10.0,
                is_bold=False,
                line_count=1,
                confidence="high",
            ),
            PaperLayoutBlock(
                block_id="page:1:block:3",
                page=1,
                block_type="text",
                text="2 Method",
                bbox=[72.0, 140.0, 180.0, 158.0],
                column=1,
                font_size=13.0,
                is_bold=True,
                line_count=1,
                confidence="high",
            ),
            PaperLayoutBlock(
                block_id="page:1:block:4",
                page=1,
                block_type="formula_candidate",
                text="E = mc^2 (1)",
                bbox=[90.0, 180.0, 210.0, 198.0],
                column=1,
                font_size=10.0,
                is_bold=False,
                line_count=1,
                confidence="high",
            ),
            PaperLayoutBlock(
                block_id="page:1:block:5",
                page=1,
                block_type="text",
                text="Table 1 Results",
                bbox=[72.0, 230.0, 220.0, 248.0],
                column=1,
                font_size=10.0,
                is_bold=True,
                line_count=1,
                confidence="high",
            ),
            PaperLayoutBlock(
                block_id="page:1:block:6",
                page=1,
                block_type="table_candidate",
                text="Method  PSNR  SSIM\nOurs    31.0  0.91",
                bbox=[72.0, 255.0, 360.0, 295.0],
                column=1,
                font_size=10.0,
                is_bold=False,
                line_count=2,
                confidence="high",
            ),
        ]

        sections = reader.detect_sections_from_layout(blocks)
        tables = reader.detect_tables_from_layout(blocks, sections)
        formulas = reader.detect_formulas_from_layout(blocks, sections)

        self.assertGreaterEqual(len(sections), 2)
        self.assertEqual(sections[0].bbox, [72.0, 90.0, 420.0, 110.0])
        self.assertEqual(sections[0].extraction_method, "pymupdf_layout")
        self.assertEqual(tables[0].caption, "Table 1 Results")
        self.assertEqual(tables[0].bbox, [72.0, 255.0, 360.0, 295.0])
        self.assertEqual(tables[0].extraction_method, "pymupdf_layout")
        self.assertEqual(formulas[0].bbox, [90.0, 180.0, 210.0, 198.0])
        self.assertEqual(formulas[0].extraction_method, "pymupdf_layout")


if __name__ == "__main__":
    unittest.main()
