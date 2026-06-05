from __future__ import annotations

import csv
import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PaperClaim:
    claim: str
    claim_type: str
    evidence_text: str
    section: str
    page: int | None
    confidence: str


@dataclass
class PaperSection:
    section_id: str
    heading: str
    normalized_heading: str
    page_start: int | None
    page_end: int | None
    text: str
    bbox: list[float] = field(default_factory=list)
    column: int | None = None
    confidence: str = "medium"
    extraction_method: str = "text_heuristic"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperTable:
    table_id: str
    section: str
    page: int | None
    caption: str
    text: str
    confidence: str
    bbox: list[float] = field(default_factory=list)
    extraction_method: str = "text_heuristic"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperFormula:
    formula_id: str
    section: str
    page: int | None
    text: str
    confidence: str
    bbox: list[float] = field(default_factory=list)
    extraction_method: str = "text_heuristic"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperLayoutBlock:
    block_id: str
    page: int
    block_type: str
    text: str
    bbox: list[float]
    column: int | None
    font_size: float | None
    is_bold: bool
    line_count: int
    confidence: str


@dataclass
class PaperReading:
    paper_id: str
    paper_title: str
    bibliographic_info: dict[str, Any]
    full_text_available: bool
    read_source: str
    problem: str
    motivation: str
    method: str
    architecture: str
    input_output: str
    dataset: str
    metrics: str
    main_results: str
    limitations: str
    reproducibility: str
    related_papers: list[str]
    claims: list[PaperClaim] = field(default_factory=list)
    layout_blocks: list[PaperLayoutBlock] = field(default_factory=list)
    sections: list[PaperSection] = field(default_factory=list)
    tables: list[PaperTable] = field(default_factory=list)
    formulas: list[PaperFormula] = field(default_factory=list)


@dataclass
class PaperReaderResult:
    paper_readings_jsonl: str
    paper_reading_report_md: str
    paper_fulltext_chunks_jsonl: str
    paper_layout_blocks_jsonl: str
    paper_sections_jsonl: str
    paper_tables_jsonl: str
    paper_structured_tables_jsonl: str
    paper_structured_tables_csv: str
    paper_formulas_jsonl: str
    paper_count: int
    abstract_only_count: int
    full_text_count: int
    claim_count: int
    layout_block_count: int
    section_count: int
    table_count: int
    structured_table_count: int
    formula_count: int


class PaperReader:
    """Read ranked papers using metadata, abstracts, and layout-aware PDF text."""

    def read_core_sources(self, task_input: dict[str, Any], output_dir: Path | str) -> PaperReaderResult:
        output_path = Path(output_dir)
        ranked_csv = Path(str(task_input.get("ranked_papers_csv") or output_path / "ranked_papers.csv"))
        if not ranked_csv.exists():
            raise FileNotFoundError(f"ranked_papers.csv not found: {ranked_csv}")

        max_papers = int(task_input.get("max_papers", 10))
        rows = self.read_ranked_papers(ranked_csv)
        selected = [
            row for row in rows if row.get("decision") in {"include", "maybe"}
        ][:max_papers]
        readings = [self.read_one(row, output_path=output_path, task_input=task_input) for row in selected]
        chunks = self.full_text_chunks(readings)
        layout_blocks = self.layout_block_rows(readings)
        sections = self.section_rows(readings)
        tables = self.table_rows(readings)
        structured_tables = self.structured_table_rows(readings)
        formulas = self.formula_rows(readings)

        readings_path = output_path / "paper_readings.jsonl"
        report_path = output_path / "paper_reading_report.md"
        chunks_path = output_path / "paper_fulltext_chunks.jsonl"
        layout_blocks_path = output_path / "paper_layout_blocks.jsonl"
        sections_path = output_path / "paper_sections.jsonl"
        tables_path = output_path / "paper_tables.jsonl"
        structured_tables_jsonl_path = output_path / "paper_structured_tables.jsonl"
        structured_tables_csv_path = output_path / "paper_structured_tables.csv"
        formulas_path = output_path / "paper_formulas.jsonl"
        self.write_jsonl(readings, readings_path)
        self.write_dict_jsonl(chunks, chunks_path)
        self.write_dict_jsonl(layout_blocks, layout_blocks_path)
        self.write_dict_jsonl(sections, sections_path)
        self.write_dict_jsonl(tables, tables_path)
        self.write_dict_jsonl(structured_tables, structured_tables_jsonl_path)
        self.write_structured_table_csv(structured_tables, structured_tables_csv_path)
        self.write_dict_jsonl(formulas, formulas_path)
        self.write_report(readings, report_path)

        return PaperReaderResult(
            paper_readings_jsonl=str(readings_path),
            paper_reading_report_md=str(report_path),
            paper_fulltext_chunks_jsonl=str(chunks_path),
            paper_layout_blocks_jsonl=str(layout_blocks_path),
            paper_sections_jsonl=str(sections_path),
            paper_tables_jsonl=str(tables_path),
            paper_structured_tables_jsonl=str(structured_tables_jsonl_path),
            paper_structured_tables_csv=str(structured_tables_csv_path),
            paper_formulas_jsonl=str(formulas_path),
            paper_count=len(readings),
            abstract_only_count=sum(1 for reading in readings if not reading.full_text_available),
            full_text_count=sum(1 for reading in readings if reading.full_text_available),
            claim_count=sum(len(reading.claims) for reading in readings),
            layout_block_count=len(layout_blocks),
            section_count=len(sections),
            table_count=len(tables),
            structured_table_count=len(structured_tables),
            formula_count=len(formulas),
        )

    @staticmethod
    def read_ranked_papers(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def read_one(self, row: dict[str, str], output_path: Path | None = None, task_input: dict[str, Any] | None = None) -> PaperReading:
        title = row.get("title", "").strip()
        abstract = row.get("abstract", "").strip()
        pdf_text, read_source, layout_blocks, sections, tables, formulas = self.load_full_text(
            row,
            output_path=output_path,
            task_input=task_input or {},
        )
        text = pdf_text or f"{title}. {abstract}".strip()
        claims = self.extract_claims_from_sections(sections) if sections else self.extract_claims(
            text=text,
            paper_id=row.get("paper_id", ""),
            section="abstract",
        )

        return PaperReading(
            paper_id=row.get("paper_id", ""),
            paper_title=title,
            bibliographic_info={
                "authors": row.get("authors", ""),
                "year": row.get("year", ""),
                "venue": row.get("venue", ""),
                "doi": row.get("doi", ""),
                "arxiv_id": row.get("arxiv_id", ""),
                "url": row.get("url", ""),
                "source": row.get("source", ""),
                "pdf_url": row.get("pdf_url", ""),
                "local_pdf_path": row.get("local_pdf_path", ""),
            },
            full_text_available=bool(pdf_text),
            read_source=read_source if pdf_text else "abstract_metadata_only",
            problem=self.extract_problem(text),
            motivation=self.extract_motivation(text),
            method=self.extract_method(text),
            architecture=self.extract_architecture(text),
            input_output=self.extract_input_output(text),
            dataset=self.extract_dataset(text),
            metrics=self.extract_metrics(text),
            main_results=self.extract_results(text),
            limitations=self.extract_limitations(text),
            reproducibility=self.extract_reproducibility(text),
            related_papers=self.extract_related_papers(text),
            claims=claims,
            layout_blocks=layout_blocks,
            sections=sections,
            tables=tables,
            formulas=formulas,
        )

    @staticmethod
    def sentence_split(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [part.strip() for part in parts if part.strip()]

    def find_sentence(self, text: str, keywords: list[str]) -> str:
        for sentence in self.sentence_split(text):
            lower = sentence.lower()
            if any(keyword in lower for keyword in keywords):
                return sentence
        return ""

    def extract_problem(self, text: str) -> str:
        return self.find_sentence(text, ["problem", "challenge", "limitation", "difficulty"])

    def extract_motivation(self, text: str) -> str:
        return self.find_sentence(text, ["motivat", "need", "aim", "goal", "to address"])

    def extract_method(self, text: str) -> str:
        return self.find_sentence(text, ["propose", "present", "introduce", "method", "approach"])

    def extract_architecture(self, text: str) -> str:
        return self.find_sentence(text, ["network", "architecture", "module", "field", "neural"])

    def extract_input_output(self, text: str) -> str:
        return self.find_sentence(text, ["input", "output", "given", "estimate", "predict"])

    def extract_dataset(self, text: str) -> str:
        return self.find_sentence(text, ["dataset", "benchmark", "data", "phototourism", "synthetic"])

    def extract_metrics(self, text: str) -> str:
        return self.find_sentence(text, ["metric", "accuracy", "psnr", "ssim", "lpips", "performance"])

    def extract_results(self, text: str) -> str:
        return self.find_sentence(text, ["result", "achieve", "outperform", "superior", "improve"])

    def extract_limitations(self, text: str) -> str:
        limitation = self.find_sentence(text, ["limited", "limitation", "fail", "difficulty"])
        if limitation:
            return limitation
        return "Not available from title/abstract metadata."

    def extract_reproducibility(self, text: str) -> str:
        code_sentence = self.find_sentence(text, ["code", "github", "available at", "dataset"])
        if code_sentence:
            return code_sentence
        return "No code or dataset availability statement found in available metadata."

    @staticmethod
    def extract_related_papers(text: str) -> list[str]:
        candidates = re.findall(r"\b(?:NeRF|Instant-NGP|Mip-NeRF|BARF|BANF|DVGO|PlenOctrees)\b", text)
        return list(dict.fromkeys(candidates))

    def extract_claims(self, text: str, paper_id: str, section: str = "abstract", page: int | None = None) -> list[PaperClaim]:
        claims: list[PaperClaim] = []
        for sentence in self.sentence_split(text):
            lower = sentence.lower()
            if any(keyword in lower for keyword in ["propose", "present", "introduce"]):
                claims.append(
                    PaperClaim(
                        claim=sentence,
                        claim_type="author_claim",
                        evidence_text=sentence,
                        section=section,
                        page=page,
                        confidence="high" if section == "full_text" else "medium",
                    )
                )
            elif any(keyword in lower for keyword in ["achieve", "outperform", "superior", "improve"]):
                claims.append(
                    PaperClaim(
                        claim=sentence,
                        claim_type="finding",
                        evidence_text=sentence,
                        section=section,
                        page=page,
                        confidence="high" if section == "full_text" else "medium",
                    )
                )
        if not claims and text:
            first = self.sentence_split(text)[0]
            claims.append(
                PaperClaim(
                    claim=first,
                    claim_type="metadata_summary",
                    evidence_text=first,
                    section=section if section == "full_text" else "title_or_abstract",
                    page=page,
                    confidence="low",
                )
            )
        return claims

    def extract_claims_from_sections(self, sections: list[PaperSection]) -> list[PaperClaim]:
        claims: list[PaperClaim] = []
        for section in sections:
            claims.extend(
                self.extract_claims(
                    text=section.text,
                    paper_id="",
                    section=section.normalized_heading or section.heading or "full_text",
                    page=section.page_start,
                )
            )
        return claims

    def load_full_text(
        self,
        row: dict[str, str],
        output_path: Path | None,
        task_input: dict[str, Any],
    ) -> tuple[str, str, list[PaperLayoutBlock], list[PaperSection], list[PaperTable], list[PaperFormula]]:
        local_pdf_path = str(row.get("local_pdf_path") or "").strip()
        pdf_url = str(row.get("pdf_url") or "").strip()
        allow_download = bool(task_input.get("download_pdfs", False))
        pdf_path: Path | None = Path(local_pdf_path).expanduser() if local_pdf_path else None
        if pdf_path and not pdf_path.exists():
            pdf_path = None
        if not pdf_path and allow_download and pdf_url and output_path:
            pdf_path = self.download_pdf(pdf_url=pdf_url, output_path=output_path, paper_id=row.get("paper_id", ""))
        if not pdf_path:
            return "", "abstract_metadata_only", [], [], [], []
        text, parser, layout_blocks, sections, tables, formulas = self.extract_pdf_structure(pdf_path)
        return (
            text,
            f"pdf_full_text:{parser}" if text else "abstract_metadata_only",
            layout_blocks,
            sections,
            tables,
            formulas,
        )

    def download_pdf(self, pdf_url: str, output_path: Path, paper_id: str) -> Path | None:
        pdf_dir = output_path / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^\w.-]+", "_", paper_id or "paper")
        target = pdf_dir / f"{safe_id}.pdf"
        request = urllib.request.Request(pdf_url, headers={"User-Agent": "AutoResearchPaperReader/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                target.write_bytes(response.read())
            return target
        except Exception:  # noqa: BLE001 - download failure falls back to metadata read.
            return None

    def extract_pdf_structure(
        self,
        path: Path,
    ) -> tuple[str, str, list[PaperLayoutBlock], list[PaperSection], list[PaperTable], list[PaperFormula]]:
        try:
            import fitz  # type: ignore

            page_texts: list[dict[str, Any]] = []
            layout_blocks: list[PaperLayoutBlock] = []
            with fitz.open(path) as document:
                for page_index, page in enumerate(document, start=1):
                    page_dict = page.get_text("dict")
                    layout_blocks.extend(self.extract_layout_blocks(page_dict, page_number=page_index))
                    text = page.get_text("text")
                    if text.strip():
                        page_texts.append({"page": page_index, "text": text})
            if layout_blocks:
                page_texts = self.page_texts_from_layout_blocks(layout_blocks)
            text = "\n".join(f"[page {item['page']}]\n{item['text']}" for item in page_texts).strip()
            sections = self.detect_sections_from_layout(layout_blocks) if layout_blocks else self.detect_sections(page_texts)
            tables = self.detect_tables_from_layout(layout_blocks, sections) if layout_blocks else self.detect_tables(sections)
            formulas = self.detect_formulas_from_layout(layout_blocks, sections) if layout_blocks else self.detect_formulas(sections)
            return text, "pymupdf_layout", layout_blocks, sections, tables, formulas
        except Exception:
            raw = path.read_bytes()
            decoded = raw.decode("utf-8", errors="ignore")
            text = "\n".join(line.strip() for line in decoded.splitlines()).strip()
            if "%PDF" in text[:20] and len(text) < 200:
                return "", "fallback_failed", [], [], [], []
            layout_blocks = self.layout_blocks_from_plain_text(text) if text else []
            sections = self.detect_sections([{"page": 1, "text": text}]) if text else []
            tables = self.detect_tables(sections)
            formulas = self.detect_formulas(sections)
            return text, "fallback_text_decode", layout_blocks, sections, tables, formulas

    def extract_pdf_text(self, path: Path) -> tuple[str, str]:
        text, parser, _, _, _, _ = self.extract_pdf_structure(path)
        return text, parser

    def extract_layout_blocks(self, page_dict: dict[str, Any], page_number: int) -> list[PaperLayoutBlock]:
        page_width = float(page_dict.get("width") or 0.0)
        raw_blocks = page_dict.get("blocks") if isinstance(page_dict, dict) else []
        blocks: list[PaperLayoutBlock] = []
        for block_index, block in enumerate(raw_blocks if isinstance(raw_blocks, list) else [], start=1):
            if not isinstance(block, dict):
                continue
            lines = block.get("lines")
            if not isinstance(lines, list):
                continue
            text_lines: list[str] = []
            sizes: list[float] = []
            fonts: list[str] = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                line_parts: list[str] = []
                spans = line.get("spans")
                if not isinstance(spans, list):
                    continue
                for span in spans:
                    if not isinstance(span, dict):
                        continue
                    span_text = str(span.get("text") or "")
                    if span_text:
                        line_parts.append(span_text)
                    if span.get("size") is not None:
                        sizes.append(float(span.get("size") or 0.0))
                    if span.get("font"):
                        fonts.append(str(span.get("font") or ""))
                line_text = "".join(line_parts).strip()
                if line_text:
                    text_lines.append(line_text)
            text = "\n".join(text_lines).strip()
            if not text:
                continue
            bbox = self.normalize_bbox(block.get("bbox"))
            column = self.estimate_column(bbox, page_width)
            font_size = round(sum(sizes) / len(sizes), 2) if sizes else None
            is_bold = any("bold" in font.lower() for font in fonts)
            block_type = "table_candidate" if self.block_looks_like_table(text) else "text"
            if self.block_looks_like_formula(text):
                block_type = "formula_candidate"
            blocks.append(
                PaperLayoutBlock(
                    block_id=f"page:{page_number}:block:{block_index}",
                    page=page_number,
                    block_type=block_type,
                    text=text,
                    bbox=bbox,
                    column=column,
                    font_size=font_size,
                    is_bold=is_bold,
                    line_count=len(text_lines),
                    confidence="high" if bbox else "medium",
                )
            )
        return sorted(blocks, key=lambda item: (item.page, item.bbox[1] if item.bbox else 0.0, item.bbox[0] if item.bbox else 0.0))

    @staticmethod
    def normalize_bbox(value: Any) -> list[float]:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return []
        return [round(float(item), 2) for item in value]

    @staticmethod
    def estimate_column(bbox: list[float], page_width: float) -> int | None:
        if not bbox or page_width <= 0:
            return None
        center_x = (bbox[0] + bbox[2]) / 2.0
        return 1 if center_x < page_width / 2.0 else 2

    @staticmethod
    def page_texts_from_layout_blocks(blocks: list[PaperLayoutBlock]) -> list[dict[str, Any]]:
        by_page: dict[int, list[PaperLayoutBlock]] = {}
        for block in blocks:
            by_page.setdefault(block.page, []).append(block)
        return [
            {
                "page": page,
                "text": "\n".join(block.text for block in sorted(items, key=lambda item: (item.bbox[1] if item.bbox else 0.0, item.bbox[0] if item.bbox else 0.0))),
            }
            for page, items in sorted(by_page.items())
        ]

    def layout_blocks_from_plain_text(self, text: str) -> list[PaperLayoutBlock]:
        blocks: list[PaperLayoutBlock] = []
        for index, paragraph in enumerate(re.split(r"\n\s*\n", text), start=1):
            cleaned = "\n".join(line.strip() for line in paragraph.splitlines() if line.strip()).strip()
            if not cleaned:
                continue
            block_type = "table_candidate" if self.block_looks_like_table(cleaned) else "text"
            if self.block_looks_like_formula(cleaned):
                block_type = "formula_candidate"
            blocks.append(
                PaperLayoutBlock(
                    block_id=f"page:1:block:{index}",
                    page=1,
                    block_type=block_type,
                    text=cleaned,
                    bbox=[],
                    column=None,
                    font_size=None,
                    is_bold=False,
                    line_count=len(cleaned.splitlines()),
                    confidence="low",
                )
            )
        return blocks

    def detect_sections_from_layout(self, blocks: list[PaperLayoutBlock]) -> list[PaperSection]:
        if not blocks:
            return []
        body_sizes = [block.font_size for block in blocks if block.font_size and len(block.text) > 40]
        body_size = sorted(body_sizes)[len(body_sizes) // 2] if body_sizes else None
        sections: list[PaperSection] = []
        current_heading = "Full Text"
        current_normalized = "full_text"
        current_page: int | None = None
        current_column: int | None = None
        current_blocks: list[PaperLayoutBlock] = []
        section_index = 1

        def flush(page_end: int | None) -> None:
            nonlocal section_index, current_blocks, current_heading, current_normalized, current_page, current_column
            text = "\n".join(block.text for block in current_blocks).strip()
            if not text:
                return
            bbox = self.union_bbox([block.bbox for block in current_blocks])
            sections.append(
                PaperSection(
                    section_id=f"section:{section_index}",
                    heading=current_heading,
                    normalized_heading=current_normalized,
                    page_start=current_page,
                    page_end=page_end,
                    text=text,
                    bbox=bbox,
                    column=current_column,
                    confidence="high" if bbox else "medium",
                    extraction_method="pymupdf_layout",
                    evidence={
                        "block_ids": [block.block_id for block in current_blocks],
                        "body_font_size": body_size,
                    },
                )
            )
            section_index += 1
            current_blocks = []

        last_page = blocks[-1].page if blocks else None
        for block in blocks:
            heading = self.detect_layout_heading(block, body_size)
            if heading:
                flush(page_end=block.page)
                current_heading = heading
                current_normalized = self.normalize_heading(heading)
                current_page = block.page
                current_column = block.column
                continue
            if current_page is None:
                current_page = block.page
                current_column = block.column
            current_blocks.append(block)
        flush(page_end=last_page)
        return sections or self.detect_sections(self.page_texts_from_layout_blocks(blocks))

    def detect_layout_heading(self, block: PaperLayoutBlock, body_size: float | None) -> str:
        one_line = re.sub(r"\s+", " ", block.text).strip()
        direct = self.detect_heading(one_line)
        if direct:
            return direct
        if "\n" in block.text or len(one_line) > 90:
            return ""
        if body_size and block.font_size and block.font_size >= body_size + 1.2 and len(one_line.split()) <= 10:
            return one_line
        if block.is_bold and 1 <= len(one_line.split()) <= 10 and not one_line.endswith("."):
            return one_line
        return ""

    def detect_tables_from_layout(
        self,
        blocks: list[PaperLayoutBlock],
        sections: list[PaperSection],
    ) -> list[PaperTable]:
        tables: list[PaperTable] = []
        for index, block in enumerate(blocks):
            if not self.block_looks_like_table(block.text):
                continue
            if self.block_is_table_caption_only(block.text):
                continue
            nearby_caption = self.nearby_caption(blocks, index, prefix_pattern=r"^(table|tab\.)\s*\d+")
            section = self.section_for_block(block, sections)
            tables.append(
                PaperTable(
                    table_id=f"{section.section_id if section else 'layout'}:table:{len(tables) + 1}",
                    section=section.normalized_heading if section else "full_text",
                    page=block.page,
                    caption=nearby_caption,
                    text=block.text,
                    confidence="high" if block.bbox and nearby_caption else "medium",
                    bbox=block.bbox,
                    extraction_method="pymupdf_layout",
                    evidence={
                        "block_id": block.block_id,
                        "line_count": block.line_count,
                        "column": block.column,
                        "reason": "grid-like numeric layout or table caption detected from PDF block geometry",
                    },
                )
            )
        if tables:
            return tables
        return self.detect_tables(sections)

    def detect_formulas_from_layout(
        self,
        blocks: list[PaperLayoutBlock],
        sections: list[PaperSection],
    ) -> list[PaperFormula]:
        formulas: list[PaperFormula] = []
        for block in blocks:
            for line_index, line in enumerate(block.text.splitlines(), start=1):
                stripped = line.strip()
                if not self.looks_like_formula_line(stripped):
                    continue
                section = self.section_for_block(block, sections)
                formulas.append(
                    PaperFormula(
                        formula_id=f"{section.section_id if section else 'layout'}:formula:{len(formulas) + 1}",
                        section=section.normalized_heading if section else "full_text",
                        page=block.page,
                        text=stripped,
                        confidence="high" if block.bbox else "medium",
                        bbox=block.bbox,
                        extraction_method="pymupdf_layout",
                        evidence={
                            "block_id": block.block_id,
                            "line_index": line_index,
                            "reason": "formula-like symbols detected with PDF block geometry",
                        },
                    )
                )
        if formulas:
            return formulas
        return self.detect_formulas(sections)

    def section_for_block(self, block: PaperLayoutBlock, sections: list[PaperSection]) -> PaperSection | None:
        for section in sections:
            if block.block_id in section.evidence.get("block_ids", []):
                return section
            if section.page_start and section.page_end and section.page_start <= block.page <= section.page_end:
                if not section.bbox or not block.bbox or self.bbox_overlap(section.bbox, block.bbox) > 0:
                    return section
        return sections[-1] if sections else None

    @staticmethod
    def union_bbox(boxes: list[list[float]]) -> list[float]:
        valid = [box for box in boxes if len(box) == 4]
        if not valid:
            return []
        return [
            round(min(box[0] for box in valid), 2),
            round(min(box[1] for box in valid), 2),
            round(max(box[2] for box in valid), 2),
            round(max(box[3] for box in valid), 2),
        ]

    @staticmethod
    def bbox_overlap(left: list[float], right: list[float]) -> float:
        if len(left) != 4 or len(right) != 4:
            return 0.0
        x1 = max(left[0], right[0])
        y1 = max(left[1], right[1])
        x2 = min(left[2], right[2])
        y2 = min(left[3], right[3])
        if x2 <= x1 or y2 <= y1:
            return 0.0
        overlap = (x2 - x1) * (y2 - y1)
        right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1.0)
        return overlap / right_area

    def nearby_caption(self, blocks: list[PaperLayoutBlock], index: int, prefix_pattern: str) -> str:
        for offset in [-2, -1, 0, 1]:
            candidate_index = index + offset
            if candidate_index < 0 or candidate_index >= len(blocks):
                continue
            first_line = blocks[candidate_index].text.splitlines()[0].strip()
            if re.match(prefix_pattern, first_line, flags=re.IGNORECASE):
                return first_line
        return ""

    def block_looks_like_table(self, text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return False
        if re.match(r"^(table|tab\.)\s*\d+", lines[0], flags=re.IGNORECASE):
            return True
        table_like = [line for line in lines if self.looks_like_table_line(line)]
        numeric_lines = [line for line in lines if len(self.extract_numbers(line)) >= 2]
        return len(table_like) >= 1 or (len(lines) >= 2 and len(numeric_lines) >= 2)

    def block_looks_like_formula(self, text: str) -> bool:
        return any(self.looks_like_formula_line(line.strip()) for line in text.splitlines())

    @staticmethod
    def block_is_table_caption_only(text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) != 1:
            return False
        return bool(re.match(r"^(table|tab\.)\s*\d+", lines[0], flags=re.IGNORECASE))

    def detect_sections(self, page_texts: list[dict[str, Any]]) -> list[PaperSection]:
        sections: list[PaperSection] = []
        current_heading = "Full Text"
        current_normalized = "full_text"
        current_page: int | None = None
        buffer: list[str] = []
        section_index = 1

        def flush(page_end: int | None) -> None:
            nonlocal section_index, buffer, current_heading, current_normalized, current_page
            text = "\n".join(buffer).strip()
            if not text:
                return
            sections.append(
                PaperSection(
                    section_id=f"section:{section_index}",
                    heading=current_heading,
                    normalized_heading=current_normalized,
                    page_start=current_page,
                    page_end=page_end,
                    text=text,
                )
            )
            section_index += 1
            buffer = []

        last_page: int | None = None
        for page_item in page_texts:
            page = int(page_item.get("page") or 0) or None
            last_page = page
            for raw_line in str(page_item.get("text") or "").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                heading = self.detect_heading(line)
                if heading:
                    flush(page_end=page)
                    current_heading = heading
                    current_normalized = self.normalize_heading(heading)
                    current_page = page
                    continue
                if current_page is None:
                    current_page = page
                buffer.append(line)
        flush(page_end=last_page)
        return sections

    @staticmethod
    def detect_heading(line: str) -> str:
        cleaned = line.strip()
        if len(cleaned) > 90:
            return ""
        if re.search(r"\s{2,}", cleaned):
            return ""
        heading_patterns = [
            r"^(abstract|introduction|related work|background|method|methods|approach|experiments?|results?|evaluation|discussion|limitations?|conclusion|references|appendix)\b",
            r"^\d+(\.\d+)*\s+(introduction|related work|background|method|methods|approach|experiments?|results?|evaluation|discussion|limitations?|conclusion|appendix)\b",
        ]
        lower = cleaned.lower()
        if any(re.match(pattern, lower) for pattern in heading_patterns):
            return cleaned
        if cleaned.isupper() and 3 <= len(cleaned.split()) <= 8:
            return cleaned.title()
        return ""

    @staticmethod
    def normalize_heading(heading: str) -> str:
        lower = re.sub(r"^\d+(\.\d+)*\s+", "", heading.lower()).strip()
        if "abstract" in lower:
            return "abstract"
        if "intro" in lower:
            return "introduction"
        if "related" in lower or "background" in lower:
            return "related_work"
        if "method" in lower or "approach" in lower:
            return "method"
        if "experiment" in lower or "evaluation" in lower:
            return "experiment"
        if "result" in lower:
            return "results"
        if "limitation" in lower or "discussion" in lower:
            return "discussion"
        if "conclusion" in lower:
            return "conclusion"
        if "reference" in lower:
            return "references"
        if "appendix" in lower:
            return "appendix"
        return re.sub(r"[^a-z0-9]+", "_", lower).strip("_") or "full_text"

    def detect_tables(self, sections: list[PaperSection]) -> list[PaperTable]:
        tables: list[PaperTable] = []
        for section in sections:
            lines = section.text.splitlines()
            for index, line in enumerate(lines):
                lower = line.lower().strip()
                looks_like_caption = re.match(r"^(table|tab\.)\s*\d+", lower)
                looks_like_grid = self.looks_like_table_line(line)
                if not (looks_like_caption or looks_like_grid):
                    continue
                context = "\n".join(lines[index : min(len(lines), index + 8)]).strip()
                tables.append(
                    PaperTable(
                        table_id=f"{section.section_id}:table:{len(tables) + 1}",
                        section=section.normalized_heading,
                        page=section.page_start,
                        caption=line.strip() if looks_like_caption else "",
                        text=context,
                        confidence="medium" if looks_like_caption else "low",
                    )
                )
        return tables

    @staticmethod
    def looks_like_table_line(line: str) -> bool:
        stripped = line.strip()
        if "|" in stripped and stripped.count("|") >= 2:
            return True
        columns = re.split(r"\s{2,}", stripped)
        numeric_columns = sum(1 for column in columns if re.search(r"\d", column))
        return len(columns) >= 3 and numeric_columns >= 2

    def detect_formulas(self, sections: list[PaperSection]) -> list[PaperFormula]:
        formulas: list[PaperFormula] = []
        for section in sections:
            for line in section.text.splitlines():
                stripped = line.strip()
                if not self.looks_like_formula_line(stripped):
                    continue
                formulas.append(
                    PaperFormula(
                        formula_id=f"{section.section_id}:formula:{len(formulas) + 1}",
                        section=section.normalized_heading,
                        page=section.page_start,
                        text=stripped,
                        confidence="medium",
                    )
                )
        return formulas

    @staticmethod
    def looks_like_formula_line(line: str) -> bool:
        if len(line) > 180:
            return False
        math_tokens = ["=", "\\", "∑", "Σ", "∫", "√", "≤", "≥", "argmin", "argmax", "log", "exp"]
        has_math = any(token in line for token in math_tokens)
        has_symbolic_var = bool(re.search(r"\b[a-zA-Z]\s*[=<>]\s*[-+a-zA-Z0-9]", line))
        numbered = bool(re.search(r"\(\s*\d+\s*\)\s*$", line))
        return has_math and (has_symbolic_var or numbered or len(re.findall(r"[+\-*/^]", line)) >= 2)

    @staticmethod
    def full_text_chunks(readings: list[PaperReading]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            if reading.sections:
                for section in reading.sections:
                    rows.append(
                        {
                            "paper_id": reading.paper_id,
                            "paper_title": reading.paper_title,
                            "chunk_id": f"{reading.paper_id}:{section.section_id}",
                            "section": section.normalized_heading,
                            "heading": section.heading,
                            "page_start": section.page_start,
                            "page_end": section.page_end,
                            "text": section.text,
                        }
                    )
            else:
                for index, claim in enumerate(reading.claims, start=1):
                    if claim.section == "full_text":
                        rows.append(
                            {
                                "paper_id": reading.paper_id,
                                "paper_title": reading.paper_title,
                                "chunk_id": f"{reading.paper_id}:chunk:{index}",
                                "section": claim.section,
                                "page_start": claim.page,
                                "page_end": claim.page,
                                "text": claim.evidence_text,
                        }
                    )
        return rows

    @staticmethod
    def layout_block_rows(readings: list[PaperReading]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            for block in reading.layout_blocks:
                row = asdict(block)
                row.update({"paper_id": reading.paper_id, "paper_title": reading.paper_title})
                rows.append(row)
        return rows

    @staticmethod
    def section_rows(readings: list[PaperReading]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            for section in reading.sections:
                row = asdict(section)
                row.update({"paper_id": reading.paper_id, "paper_title": reading.paper_title})
                rows.append(row)
        return rows

    @staticmethod
    def table_rows(readings: list[PaperReading]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            for table in reading.tables:
                row = asdict(table)
                row.update({"paper_id": reading.paper_id, "paper_title": reading.paper_title})
                rows.append(row)
        return rows

    @staticmethod
    def formula_rows(readings: list[PaperReading]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            for formula in reading.formulas:
                row = asdict(formula)
                row.update({"paper_id": reading.paper_id, "paper_title": reading.paper_title})
                rows.append(row)
        return rows

    def structured_table_rows(self, readings: list[PaperReading]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for reading in readings:
            for table in reading.tables:
                parsed = self.parse_table_candidate(table.text)
                if not parsed["rows"]:
                    continue
                rows.append(
                    {
                        "paper_id": reading.paper_id,
                        "paper_title": reading.paper_title,
                        "table_id": table.table_id,
                        "section": table.section,
                        "page": table.page,
                        "caption": table.caption or parsed["caption"],
                        "headers": parsed["headers"],
                        "rows": parsed["rows"],
                        "numeric_cell_count": parsed["numeric_cell_count"],
                        "confidence": parsed["confidence"],
                        "notes": parsed["notes"],
                    }
                )
        return rows

    def parse_table_candidate(self, text: str) -> dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        caption = ""
        if lines and re.match(r"^(table|tab\.)\s*\d+", lines[0], flags=re.IGNORECASE):
            caption = lines.pop(0)
        table_lines = [line for line in lines if self.looks_like_table_line(line) or re.search(r"\s{2,}", line)]
        if len(table_lines) < 2:
            return {
                "caption": caption,
                "headers": [],
                "rows": [],
                "numeric_cell_count": 0,
                "confidence": "low",
                "notes": ["Not enough grid-like rows for structured parsing."],
            }

        split_rows = [self.split_table_line(line) for line in table_lines]
        width = max(len(row) for row in split_rows)
        split_rows = [row + [""] * (width - len(row)) for row in split_rows]
        header = split_rows[0]
        body = split_rows[1:]
        rows: list[dict[str, Any]] = []
        numeric_count = 0
        for row_index, cells in enumerate(body, start=1):
            cell_map = {}
            numeric_cells = {}
            for column_index, value in enumerate(cells):
                header_name = header[column_index] or f"column_{column_index + 1}"
                cell_map[header_name] = value
                if self.is_numeric_cell(value):
                    numeric_cells[header_name] = value
                    numeric_count += 1
            rows.append(
                {
                    "row_index": row_index,
                    "cells": cell_map,
                    "numeric_cells": numeric_cells,
                }
            )
        confidence = "medium" if numeric_count > 0 and len(header) >= 2 else "low"
        return {
            "caption": caption,
            "headers": header,
            "rows": rows,
            "numeric_cell_count": numeric_count,
            "confidence": confidence,
            "notes": ["Heuristic structured table parse from PDF text; verify against original PDF before reporting metrics."],
        }

    @staticmethod
    def split_table_line(line: str) -> list[str]:
        if "|" in line and line.count("|") >= 2:
            return [cell.strip() for cell in line.strip("|").split("|")]
        return [cell.strip() for cell in re.split(r"\s{2,}", line.strip()) if cell.strip()]

    @staticmethod
    def extract_numbers(text: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", text)))

    @staticmethod
    def is_numeric_cell(value: str) -> bool:
        return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", value.strip()))

    @staticmethod
    def write_structured_table_csv(rows: list[dict[str, Any]], path: Path) -> None:
        fieldnames = [
            "paper_id",
            "paper_title",
            "table_id",
            "caption",
            "row_index",
            "column",
            "value",
            "is_numeric",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for table in rows:
                for row in table.get("rows", []):
                    cells = row.get("cells") if isinstance(row, dict) else {}
                    if not isinstance(cells, dict):
                        continue
                    numeric_cells = row.get("numeric_cells") if isinstance(row, dict) else {}
                    if not isinstance(numeric_cells, dict):
                        numeric_cells = {}
                    for column, value in cells.items():
                        writer.writerow(
                            {
                                "paper_id": table.get("paper_id", ""),
                                "paper_title": table.get("paper_title", ""),
                                "table_id": table.get("table_id", ""),
                                "caption": table.get("caption", ""),
                                "row_index": row.get("row_index", ""),
                                "column": column,
                                "value": value,
                                "is_numeric": str(column in numeric_cells).lower(),
                            }
                        )

    @staticmethod
    def write_jsonl(readings: list[PaperReading], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for reading in readings:
                handle.write(json.dumps(asdict(reading), ensure_ascii=False) + "\n")

    @staticmethod
    def write_dict_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_report(self, readings: list[PaperReading], path: Path) -> None:
        lines = [
            "# Paper Reading Report",
            "",
            f"- papers_read: {len(readings)}",
            f"- abstract_only: {sum(1 for reading in readings if not reading.full_text_available)}",
            f"- full_text: {sum(1 for reading in readings if reading.full_text_available)}",
            f"- layout_blocks: {sum(len(reading.layout_blocks) for reading in readings)}",
            f"- sections: {sum(len(reading.sections) for reading in readings)}",
            f"- table_candidates: {sum(len(reading.tables) for reading in readings)}",
            f"- structured_table_candidates: {sum(len(self.parse_table_candidate(table.text)['rows']) > 0 for reading in readings for table in reading.tables)}",
            f"- formula_candidates: {sum(len(reading.formulas) for reading in readings)}",
            "",
            "## Scope",
            "",
            "- This reader uses local/downloaded PDFs when available; otherwise it reads title, abstract, and metadata.",
            "- `full_text_available=false` means method/experiment fields are not full-text verified.",
            "",
            "## Papers",
            "",
        ]
        for index, reading in enumerate(readings, start=1):
            lines.append(f"{index}. {reading.paper_title or '(missing title)'}")
            lines.append(f"   - paper_id: {reading.paper_id}")
            lines.append(f"   - read_source: {reading.read_source}")
            lines.append(f"   - claims: {len(reading.claims)}")
            lines.append(f"   - layout_blocks: {len(reading.layout_blocks)}")
            lines.append(f"   - sections: {len(reading.sections)}")
            lines.append(f"   - table_candidates: {len(reading.tables)}")
            lines.append(
                f"   - structured_table_candidates: {sum(1 for table in reading.tables if self.parse_table_candidate(table.text)['rows'])}"
            )
            lines.append(f"   - formula_candidates: {len(reading.formulas)}")
            if reading.method:
                lines.append(f"   - method_hint: {reading.method}")
            if reading.reproducibility:
                lines.append(f"   - reproducibility: {reading.reproducibility}")
        lines.extend(
            [
                "",
                "## Anti-Hallucination Notes",
                "",
                "- Missing fields are left empty or marked unavailable.",
                "- No PDF-only details were invented.",
                "- Layout-aware table and formula outputs include page/bbox provenance when available, but still require original-PDF verification before reporting scientific metrics.",
                "- Claims are copied from available title/abstract/full-text snippets.",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
