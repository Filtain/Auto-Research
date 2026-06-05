from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvidenceItem:
    evidence_id: str
    paper_id: str
    paper_title: str
    claim: str
    claim_type: str
    evidence_text: str
    source_type: str
    source_location: dict[str, Any]
    support_level: str
    full_text_available: bool
    read_source: str
    confidence: str


@dataclass
class EvidenceResult:
    evidence_store_jsonl: str
    source_map_json: str
    paper_count: int
    evidence_count: int
    abstract_only_count: int


class EvidenceExtractor:
    """Create source-grounded evidence records from paper reading outputs.

    This module does not verify claims. It only preserves claim text and source
    pointers from `paper_readings.jsonl` so synthesis and verification stages can
    trace every later statement back to an explicit evidence ID.
    """

    def extract_evidence(self, task_input: dict[str, Any], output_dir: Path | str) -> EvidenceResult:
        output_path = Path(output_dir)
        readings_path = Path(
            str(task_input.get("paper_readings_jsonl") or output_path / "paper_readings.jsonl")
        )
        if not readings_path.exists():
            raise FileNotFoundError(f"paper_readings.jsonl not found: {readings_path}")

        readings = self.read_jsonl(readings_path)
        evidence_items: list[EvidenceItem] = []
        source_map: dict[str, Any] = {
            "schema_version": "0.1",
            "source_file": str(readings_path),
            "papers": {},
            "evidence_sources": {},
            "notes": [
                "Evidence records are extracted from paper_readings.jsonl only.",
                "Abstract-only records must not be treated as full-text evidence.",
                "Page numbers are null when unavailable; no source locations are invented.",
            ],
        }

        for reading in readings:
            paper_id = str(reading.get("paper_id") or "").strip()
            paper_title = str(reading.get("paper_title") or "").strip()
            full_text_available = bool(reading.get("full_text_available", False))
            read_source = str(reading.get("read_source") or "unknown")
            bibliographic_info = reading.get("bibliographic_info") or {}
            if not isinstance(bibliographic_info, dict):
                bibliographic_info = {}

            source_map["papers"][paper_id] = {
                "paper_title": paper_title,
                "bibliographic_info": bibliographic_info,
                "full_text_available": full_text_available,
                "read_source": read_source,
            }

            claims = reading.get("claims") or []
            if not isinstance(claims, list):
                claims = []
            for index, claim_record in enumerate(claims, start=1):
                if not isinstance(claim_record, dict):
                    continue
                evidence_text = str(claim_record.get("evidence_text") or "").strip()
                claim_text = str(claim_record.get("claim") or evidence_text).strip()
                if not evidence_text or not claim_text:
                    continue

                evidence_id = self.evidence_id(paper_id=paper_id, index=index)
                section = str(claim_record.get("section") or "").strip() or None
                page = claim_record.get("page")
                source_location = {
                    "section": section,
                    "page": page if isinstance(page, int) else None,
                    "url": bibliographic_info.get("url") or "",
                    "read_source": read_source,
                }
                item = EvidenceItem(
                    evidence_id=evidence_id,
                    paper_id=paper_id,
                    paper_title=paper_title,
                    claim=claim_text,
                    claim_type=str(claim_record.get("claim_type") or "unknown"),
                    evidence_text=evidence_text,
                    source_type="paper",
                    source_location=source_location,
                    support_level=self.support_level(full_text_available, read_source),
                    full_text_available=full_text_available,
                    read_source=read_source,
                    confidence=str(claim_record.get("confidence") or "unknown"),
                )
                evidence_items.append(item)
                source_map["evidence_sources"][evidence_id] = {
                    "paper_id": paper_id,
                    "paper_title": paper_title,
                    "source_location": source_location,
                    "support_level": item.support_level,
                    "claim_type": item.claim_type,
                }

        evidence_path = output_path / "evidence_store.jsonl"
        source_map_path = output_path / "source_map.json"
        self.write_jsonl(evidence_items, evidence_path)
        source_map["summary"] = {
            "paper_count": len(readings),
            "evidence_count": len(evidence_items),
            "abstract_only_count": sum(
                1 for reading in readings if not bool(reading.get("full_text_available", False))
            ),
        }
        source_map_path.write_text(
            json.dumps(source_map, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return EvidenceResult(
            evidence_store_jsonl=str(evidence_path),
            source_map_json=str(source_map_path),
            paper_count=len(readings),
            evidence_count=len(evidence_items),
            abstract_only_count=source_map["summary"]["abstract_only_count"],
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
    def write_jsonl(items: list[EvidenceItem], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    @staticmethod
    def evidence_id(paper_id: str, index: int) -> str:
        safe_paper_id = (paper_id or "unknown_paper").replace("/", "_").replace(":", "_")
        return f"{safe_paper_id}:claim:{index}"

    @staticmethod
    def support_level(full_text_available: bool, read_source: str) -> str:
        if full_text_available:
            return "full_text_evidence"
        if read_source == "abstract_metadata_only":
            return "abstract_metadata_only"
        return "limited_source_evidence"
