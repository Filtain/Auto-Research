from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ClaimVerification:
    evidence_id: str
    status: str
    claim: str
    support_level: str
    issues: list[str]
    source_location: dict[str, Any]


@dataclass
class VerificationResult:
    verification_report_md: str
    verification_result_json: str
    claim_verification_jsonl: str
    unsupported_claims_jsonl: str
    citation_checks_jsonl: str
    citation_authority_checks_jsonl: str
    citation_graph_checks_jsonl: str
    numeric_table_checks_jsonl: str
    contradiction_checks_jsonl: str
    verification_passed: bool
    publication_ready: bool
    checked_claim_count: int
    unsupported_claim_count: int
    missing_evidence_count: int
    abstract_only_warning_count: int
    citation_check_count: int
    citation_authority_check_count: int
    numeric_table_check_count: int
    contradiction_check_count: int


class ClaimVerifier:
    """Verify that synthesized claims are traceable to evidence records.

    This verifier does not prove scientific truth. It enforces the current MVP's
    anti-hallucination contract: every synthesized claim ID must exist in the
    evidence store, every evidence item must keep a source pointer, and weak
    abstract-only support must be surfaced before final writing.
    """

    EVIDENCE_ID_PATTERN = re.compile(r"\[([A-Za-z0-9_.:-]+:claim:\d+)\]")

    def verify_claims(self, task_input: dict[str, Any], output_dir: Path | str) -> VerificationResult:
        output_path = Path(output_dir)
        report_path = Path(str(task_input.get("report_md") or output_path / "report.md"))
        summary_path = Path(str(task_input.get("synthesis_summary_json") or output_path / "synthesis_summary.json"))
        evidence_path = Path(str(task_input.get("evidence_store_jsonl") or output_path / "evidence_store.jsonl"))
        source_map_path = Path(str(task_input.get("source_map_json") or output_path / "source_map.json"))
        papers_raw_path = Path(str(task_input.get("papers_raw_jsonl") or output_path / "papers_raw.jsonl"))
        paper_tables_path = Path(str(task_input.get("paper_tables_jsonl") or output_path / "paper_tables.jsonl"))
        enable_authority_checks = bool(task_input.get("enable_authority_checks", False))
        authority_cache_path = Path(
            str(task_input.get("authority_cache_json") or output_path / "citation_authority_cache.json")
        )

        for required_path in [report_path, summary_path, evidence_path, source_map_path]:
            if not required_path.exists():
                raise FileNotFoundError(f"Required verification input not found: {required_path}")

        report_text = report_path.read_text(encoding="utf-8")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        evidence_items = self.read_jsonl(evidence_path)
        source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
        evidence_by_id = {
            str(item.get("evidence_id")): item
            for item in evidence_items
            if str(item.get("evidence_id") or "")
        }
        source_entries = source_map.get("evidence_sources") if isinstance(source_map, dict) else {}
        if not isinstance(source_entries, dict):
            source_entries = {}

        referenced_ids = self.referenced_evidence_ids(report_text=report_text, summary=summary)
        checks: list[ClaimVerification] = []
        unsupported: list[dict[str, Any]] = []

        for evidence_id in referenced_ids:
            item = evidence_by_id.get(evidence_id)
            if not item:
                issue = {
                    "evidence_id": evidence_id,
                    "issue": "Referenced evidence ID is missing from evidence_store.jsonl.",
                    "severity": "high",
                }
                unsupported.append(issue)
                checks.append(
                    ClaimVerification(
                        evidence_id=evidence_id,
                        status="unsupported",
                        claim="",
                        support_level="missing",
                        issues=[issue["issue"]],
                        source_location={},
                    )
                )
                continue

            issues = self.check_evidence_item(evidence_id, item, source_entries)
            status = "supported_with_warnings" if issues else "supported"
            high_issues = [issue for issue in issues if issue.startswith("HIGH:")]
            if high_issues:
                status = "unsupported"
                for issue in high_issues:
                    unsupported.append(
                        {
                            "evidence_id": evidence_id,
                            "claim": item.get("claim") or "",
                            "issue": issue.removeprefix("HIGH: "),
                            "severity": "high",
                        }
                    )

            checks.append(
                ClaimVerification(
                    evidence_id=evidence_id,
                    status=status,
                    claim=str(item.get("claim") or ""),
                    support_level=str(item.get("support_level") or "unknown"),
                    issues=issues,
                    source_location=item.get("source_location") if isinstance(item.get("source_location"), dict) else {},
                )
            )

        if not referenced_ids:
            unsupported.append(
                {
                    "evidence_id": "",
                    "issue": "No evidence IDs were referenced in report.md or synthesis_summary.json.",
                    "severity": "high",
                }
            )

        verification_passed = not unsupported and bool(referenced_ids)
        abstract_only_warning_count = sum(
            1 for check in checks if check.support_level == "abstract_metadata_only"
        )
        publication_ready = verification_passed and abstract_only_warning_count == 0

        claim_verification_path = output_path / "claim_verification.jsonl"
        unsupported_path = output_path / "unsupported_claims.jsonl"
        citation_checks_path = output_path / "citation_checks.jsonl"
        citation_authority_checks_path = output_path / "citation_authority_checks.jsonl"
        citation_graph_checks_path = output_path / "citation_graph_checks.jsonl"
        numeric_table_checks_path = output_path / "numeric_table_checks.jsonl"
        contradiction_checks_path = output_path / "contradiction_checks.jsonl"
        result_path = output_path / "verification_result.json"
        report_output_path = output_path / "verification_report.md"

        citation_checks = self.metadata_cross_checks(papers_raw_path)
        authority_checks = self.authority_cross_checks(
            papers_raw_path,
            enabled=enable_authority_checks,
            cache_path=authority_cache_path,
        )
        citation_graph_checks = self.citation_graph_checks(
            papers_raw_path,
            enabled=enable_authority_checks,
            cache_path=authority_cache_path,
        )
        numeric_table_checks = self.numeric_table_checks(evidence_items, paper_tables_path)
        contradiction_checks = self.contradiction_checks(evidence_items)
        self.write_jsonl([asdict(check) for check in checks], claim_verification_path)
        self.write_jsonl(unsupported, unsupported_path)
        self.write_jsonl(citation_checks, citation_checks_path)
        self.write_jsonl(authority_checks, citation_authority_checks_path)
        self.write_jsonl(citation_graph_checks, citation_graph_checks_path)
        self.write_jsonl(numeric_table_checks, numeric_table_checks_path)
        self.write_jsonl(contradiction_checks, contradiction_checks_path)
        result_payload = {
            "schema_version": "0.1",
            "verification_passed": verification_passed,
            "publication_ready": publication_ready,
            "checked_claim_count": len(checks),
            "unsupported_claim_count": len(unsupported),
            "missing_evidence_count": sum(1 for item in unsupported if item.get("evidence_id")),
            "abstract_only_warning_count": abstract_only_warning_count,
            "citation_check_count": len(citation_checks),
            "citation_warning_count": sum(1 for item in citation_checks if item.get("status") == "warning"),
            "citation_authority_check_count": len(authority_checks),
            "citation_authority_warning_count": sum(1 for item in authority_checks if item.get("status") == "warning"),
            "citation_authority_failed_count": sum(1 for item in authority_checks if item.get("status") == "failed"),
            "citation_authority_low_confidence_count": sum(
                1 for item in authority_checks if item.get("confidence_level") == "low"
            ),
            "citation_authority_cache_hit_count": sum(1 for item in authority_checks if item.get("cache_hit")),
            "citation_graph_check_count": len(citation_graph_checks),
            "citation_graph_edge_count": sum(len(item.get("verified_edges", [])) for item in citation_graph_checks),
            "citation_graph_warning_count": sum(1 for item in citation_graph_checks if item.get("status") == "warning"),
            "citation_graph_unknown_count": sum(1 for item in citation_graph_checks if item.get("status") == "unknown"),
            "citation_graph_cache_hit_count": sum(1 for item in citation_graph_checks if item.get("cache_hit")),
            "numeric_table_check_count": len(numeric_table_checks),
            "numeric_table_warning_count": sum(1 for item in numeric_table_checks if item.get("status") == "warning"),
            "contradiction_check_count": len(contradiction_checks),
            "contradiction_candidate_count": sum(1 for item in contradiction_checks if item.get("status") == "candidate"),
            "authority_checks_enabled": enable_authority_checks,
            "inputs": {
                "report_md": str(report_path),
                "synthesis_summary_json": str(summary_path),
                "evidence_store_jsonl": str(evidence_path),
                "source_map_json": str(source_map_path),
                "papers_raw_jsonl": str(papers_raw_path),
                "paper_tables_jsonl": str(paper_tables_path),
                "authority_cache_json": str(authority_cache_path),
            },
            "notes": [
                "verification_passed means all referenced evidence IDs are traceable in this run.",
                "publication_ready is false when claims rely on abstract-only evidence.",
                "Authority checks verify metadata existence with external providers only when explicitly enabled.",
                "Citation graph checks verify provider-exposed reference/citation edges when available; missing graph data is uncertainty, not nonexistence.",
                "Numeric table checks and contradiction checks are heuristic QA signals, not final scientific judgments.",
            ],
        }
        result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_output_path.write_text(
            self.render_report(result_payload, checks, unsupported),
            encoding="utf-8",
        )

        return VerificationResult(
            verification_report_md=str(report_output_path),
            verification_result_json=str(result_path),
            claim_verification_jsonl=str(claim_verification_path),
            unsupported_claims_jsonl=str(unsupported_path),
            citation_checks_jsonl=str(citation_checks_path),
            citation_authority_checks_jsonl=str(citation_authority_checks_path),
            citation_graph_checks_jsonl=str(citation_graph_checks_path),
            numeric_table_checks_jsonl=str(numeric_table_checks_path),
            contradiction_checks_jsonl=str(contradiction_checks_path),
            verification_passed=verification_passed,
            publication_ready=publication_ready,
            checked_claim_count=len(checks),
            unsupported_claim_count=len(unsupported),
            missing_evidence_count=int(result_payload["missing_evidence_count"]),
            abstract_only_warning_count=abstract_only_warning_count,
            citation_check_count=len(citation_checks),
            citation_authority_check_count=len(authority_checks),
            numeric_table_check_count=len(numeric_table_checks),
            contradiction_check_count=len(contradiction_checks),
        )

    def referenced_evidence_ids(self, report_text: str, summary: dict[str, Any]) -> list[str]:
        ids = list(dict.fromkeys(self.EVIDENCE_ID_PATTERN.findall(report_text)))
        for paper in summary.get("paper_evidence", []) if isinstance(summary, dict) else []:
            if not isinstance(paper, dict):
                continue
            for evidence_id in paper.get("evidence_ids", []):
                if isinstance(evidence_id, str) and evidence_id and evidence_id not in ids:
                    ids.append(evidence_id)
        return ids

    @staticmethod
    def check_evidence_item(evidence_id: str, item: dict[str, Any], source_entries: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        if not str(item.get("claim") or "").strip():
            issues.append("HIGH: Evidence item has no claim text.")
        if not str(item.get("evidence_text") or "").strip():
            issues.append("HIGH: Evidence item has no evidence_text.")
        location = item.get("source_location")
        if not isinstance(location, dict):
            issues.append("HIGH: Evidence item has no source_location object.")
            location = {}
        if not (location.get("section") or location.get("url") or location.get("read_source")):
            issues.append("HIGH: Evidence item has no usable source pointer.")
        if evidence_id not in source_entries:
            issues.append("HIGH: Evidence ID is missing from source_map.json.")
        if item.get("support_level") == "abstract_metadata_only":
            issues.append("WARN: Evidence is abstract/metadata-only and needs full-text verification.")
        return issues

    def metadata_cross_checks(self, papers_raw_path: Path) -> list[dict[str, Any]]:
        if not papers_raw_path.exists():
            return [
                {
                    "paper_id": "",
                    "status": "warning",
                    "source": "",
                    "checks": ["papers_raw.jsonl is missing; external metadata cross-check skipped."],
                }
            ]
        checks: list[dict[str, Any]] = []
        for paper in self.read_jsonl(papers_raw_path):
            paper_id = str(paper.get("paper_id") or "")
            doi = str(paper.get("doi") or "").strip()
            arxiv_id = str(paper.get("arxiv_id") or "").strip()
            url = str(paper.get("url") or "").strip()
            issues: list[str] = []
            if doi and not re.match(r"^10\.\S+/\S+$", doi, flags=re.IGNORECASE):
                issues.append("DOI format could not be structurally validated.")
            if arxiv_id and not re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", arxiv_id):
                issues.append("arXiv ID format could not be structurally validated.")
            if url and not (url.startswith("http://") or url.startswith("https://") or Path(url).exists()):
                issues.append("URL is neither HTTP(S) nor an existing local path.")
            if not (doi or arxiv_id or url):
                issues.append("No DOI, arXiv ID, or URL is available for metadata cross-check.")
            checks.append(
                {
                    "paper_id": paper_id,
                    "title": paper.get("title") or "",
                    "source": paper.get("source") or "",
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "url": url,
                    "status": "warning" if issues else "passed",
                    "checks": issues or ["Basic identifier structure is present."],
                    "note": "This is a local structural cross-check; network authority checks can be added by provider.",
                }
            )
        return checks

    def authority_cross_checks(
        self,
        papers_raw_path: Path,
        enabled: bool = False,
        cache_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        if not enabled:
            return [
                {
                    "paper_id": "",
                    "provider": "",
                    "status": "skipped",
                    "authority_confidence": 0.0,
                    "confidence_level": "none",
                    "cache_hit": False,
                    "checks": ["External authority checks are disabled."],
                }
            ]
        if not papers_raw_path.exists():
            return [
                {
                    "paper_id": "",
                    "provider": "",
                    "status": "warning",
                    "authority_confidence": 0.0,
                    "confidence_level": "none",
                    "cache_hit": False,
                    "checks": ["papers_raw.jsonl is missing; authority checks skipped."],
                }
            ]
        cache = self.read_authority_cache(cache_path)
        checks: list[dict[str, Any]] = []
        for paper in self.read_jsonl(papers_raw_path):
            checks.extend(self.authority_checks_for_paper(paper, cache=cache))
        self.write_authority_cache(cache_path, cache)
        return checks

    def citation_graph_checks(
        self,
        papers_raw_path: Path,
        enabled: bool = False,
        cache_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        if not enabled:
            return [
                {
                    "paper_id": "",
                    "status": "skipped",
                    "cache_hit": False,
                    "checks": ["Citation graph truth checks are disabled."],
                }
            ]
        if not papers_raw_path.exists():
            return [
                {
                    "paper_id": "",
                    "status": "warning",
                    "cache_hit": False,
                    "checks": ["papers_raw.jsonl is missing; citation graph truth checks skipped."],
                }
            ]

        papers = self.read_jsonl(papers_raw_path)
        if not papers:
            return [
                {
                    "paper_id": "",
                    "status": "warning",
                    "cache_hit": False,
                    "checks": ["papers_raw.jsonl is empty; citation graph truth checks skipped."],
                }
            ]
        cache = self.read_authority_cache(cache_path)
        records = [self.citation_graph_record_for_paper(paper, cache=cache) for paper in papers]
        paper_index = self.paper_identity_index(papers)
        checks = [self.apply_citation_graph_policy(record, paper_index) for record in records]
        self.write_authority_cache(cache_path, cache)
        return checks

    def citation_graph_record_for_paper(self, paper: dict[str, Any], cache: dict[str, Any] | None = None) -> dict[str, Any]:
        paper_id = str(paper.get("paper_id") or "")
        doi = str(paper.get("doi") or "").strip()
        arxiv_id = str(paper.get("arxiv_id") or "").strip()
        title = str(paper.get("title") or "").strip()
        identifier = doi or arxiv_id or title
        if not identifier:
            return {
                "paper_id": paper_id,
                "status": "warning",
                "cache_hit": False,
                "checks": ["No DOI, arXiv ID, or title available for citation graph truth check."],
            }
        cache_key = self.authority_cache_key("citation_graph", identifier)
        if cache is not None and cache_key in cache and isinstance(cache[cache_key], dict):
            cached = dict(cache[cache_key])
            cached["cache_hit"] = True
            return cached

        openalex = self.fetch_openalex_graph_record(paper_id=paper_id, doi=doi, title=title)
        semantic = self.fetch_semantic_scholar_graph_record(paper_id=paper_id, doi=doi, arxiv_id=arxiv_id, title=title)
        record = self.merge_citation_graph_records(paper=paper, openalex=openalex, semantic=semantic)
        record["cache_hit"] = False
        if cache is not None and record.get("status") != "failed":
            cache[cache_key] = {**record, "cache_hit": False}
        return record

    def fetch_openalex_graph_record(self, paper_id: str, doi: str, title: str) -> dict[str, Any]:
        if not doi:
            return {"provider": "openalex", "status": "skipped", "checks": ["No DOI available for OpenAlex graph lookup."]}
        url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi)}"
        payload, error = self.read_json_url(url)
        if error:
            return {"provider": "openalex", "status": "failed", "error": error, "checks": ["OpenAlex graph request failed."]}
        ids = payload.get("ids") if isinstance(payload, dict) else {}
        referenced = payload.get("referenced_works") if isinstance(payload, dict) else []
        return {
            "provider": "openalex",
            "status": "passed",
            "external_id": str(payload.get("id") or "") if isinstance(payload, dict) else "",
            "doi": str(ids.get("doi") or doi) if isinstance(ids, dict) else doi,
            "title": str(payload.get("title") or "") if isinstance(payload, dict) else "",
            "referenced_external_ids": [str(item) for item in referenced] if isinstance(referenced, list) else [],
            "reference_count": len(referenced) if isinstance(referenced, list) else 0,
            "checks": ["OpenAlex graph metadata was retrieved."],
        }

    def fetch_semantic_scholar_graph_record(self, paper_id: str, doi: str, arxiv_id: str, title: str) -> dict[str, Any]:
        query_identifier = doi or (f"ARXIV:{arxiv_id}" if arxiv_id else "")
        if query_identifier:
            url = (
                "https://api.semanticscholar.org/graph/v1/paper/"
                + urllib.parse.quote(query_identifier, safe="")
                + "?fields=title,externalIds,references.paperId,references.title,citations.paperId,citations.title"
            )
        elif title:
            url = (
                "https://api.semanticscholar.org/graph/v1/paper/search?"
                + urllib.parse.urlencode({"query": title, "limit": 1, "fields": "title,externalIds,references.paperId,references.title,citations.paperId,citations.title"})
            )
        else:
            return {"provider": "semantic_scholar", "status": "skipped", "checks": ["No identifier available for Semantic Scholar graph lookup."]}
        payload, error = self.read_json_url(url)
        if error:
            return {"provider": "semantic_scholar", "status": "failed", "error": error, "checks": ["Semantic Scholar graph request failed."]}
        if "data" in payload and isinstance(payload.get("data"), list):
            payload = payload["data"][0] if payload["data"] else {}
        references = payload.get("references") if isinstance(payload, dict) else []
        citations = payload.get("citations") if isinstance(payload, dict) else []
        external_ids = payload.get("externalIds") if isinstance(payload, dict) else {}
        return {
            "provider": "semantic_scholar",
            "status": "passed",
            "external_id": str(payload.get("paperId") or "") if isinstance(payload, dict) else "",
            "doi": str(external_ids.get("DOI") or doi) if isinstance(external_ids, dict) else doi,
            "arxiv_id": str(external_ids.get("ArXiv") or arxiv_id) if isinstance(external_ids, dict) else arxiv_id,
            "title": str(payload.get("title") or "") if isinstance(payload, dict) else "",
            "referenced_external_ids": self.semantic_scholar_edge_ids(references),
            "citing_external_ids": self.semantic_scholar_edge_ids(citations),
            "referenced_titles": self.semantic_scholar_edge_titles(references),
            "citing_titles": self.semantic_scholar_edge_titles(citations),
            "reference_count": len(references) if isinstance(references, list) else 0,
            "citation_count": len(citations) if isinstance(citations, list) else 0,
            "checks": ["Semantic Scholar graph metadata was retrieved."],
        }

    @staticmethod
    def semantic_scholar_edge_ids(edges: Any) -> list[str]:
        if not isinstance(edges, list):
            return []
        return [str(edge.get("paperId") or "") for edge in edges if isinstance(edge, dict) and edge.get("paperId")]

    @staticmethod
    def semantic_scholar_edge_titles(edges: Any) -> list[str]:
        if not isinstance(edges, list):
            return []
        return [str(edge.get("title") or "") for edge in edges if isinstance(edge, dict) and edge.get("title")]

    def merge_citation_graph_records(
        self,
        paper: dict[str, Any],
        openalex: dict[str, Any],
        semantic: dict[str, Any],
    ) -> dict[str, Any]:
        provider_records = [openalex, semantic]
        failed = [item for item in provider_records if item.get("status") == "failed"]
        passed = [item for item in provider_records if item.get("status") == "passed"]
        referenced_external_ids: list[str] = []
        citing_external_ids: list[str] = []
        referenced_titles: list[str] = []
        citing_titles: list[str] = []
        for item in passed:
            referenced_external_ids.extend(str(value) for value in item.get("referenced_external_ids", []) if value)
            citing_external_ids.extend(str(value) for value in item.get("citing_external_ids", []) if value)
            referenced_titles.extend(str(value) for value in item.get("referenced_titles", []) if value)
            citing_titles.extend(str(value) for value in item.get("citing_titles", []) if value)
        status = "passed" if passed else "failed" if failed else "unknown"
        return {
            "paper_id": str(paper.get("paper_id") or ""),
            "title": str(paper.get("title") or ""),
            "doi": str(paper.get("doi") or ""),
            "arxiv_id": str(paper.get("arxiv_id") or ""),
            "status": status,
            "providers": provider_records,
            "referenced_external_ids": list(dict.fromkeys(referenced_external_ids)),
            "citing_external_ids": list(dict.fromkeys(citing_external_ids)),
            "referenced_titles": list(dict.fromkeys(referenced_titles)),
            "citing_titles": list(dict.fromkeys(citing_titles)),
            "checks": ["Merged provider citation graph records." if passed else "No provider citation graph record was available."],
        }

    def apply_citation_graph_policy(self, record: dict[str, Any], paper_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if record.get("status") == "failed":
            record["checks"] = ["Citation graph provider requests failed; this is not proof that citation edges do not exist."]
            record["verified_edges"] = []
            record["unverified_internal_edges"] = []
            record["confidence_level"] = "none"
            return record
        if record.get("status") in {"skipped", "warning"}:
            record.setdefault("verified_edges", [])
            record.setdefault("unverified_internal_edges", [])
            record.setdefault("confidence_level", "none")
            return record

        referenced_id_set = set(record.get("referenced_external_ids", []))
        citing_id_set = set(record.get("citing_external_ids", []))
        referenced_titles = [str(item) for item in record.get("referenced_titles", [])]
        citing_titles = [str(item) for item in record.get("citing_titles", [])]
        verified_edges: list[dict[str, Any]] = []
        unverified_edges: list[dict[str, Any]] = []
        source_paper_id = str(record.get("paper_id") or "")
        for target_id, target in paper_index.items():
            if target_id == source_paper_id:
                continue
            target_identifiers = set(target.get("identifiers", []))
            target_title = str(target.get("title") or "")
            cited_by_source = bool(target_identifiers & referenced_id_set) or self.title_in_graph(target_title, referenced_titles)
            source_cited_by_target = bool(target_identifiers & citing_id_set) or self.title_in_graph(target_title, citing_titles)
            if cited_by_source:
                verified_edges.append({"direction": "references", "source_paper_id": source_paper_id, "target_paper_id": target_id})
            elif source_cited_by_target:
                verified_edges.append({"direction": "cited_by", "source_paper_id": source_paper_id, "target_paper_id": target_id})
            else:
                unverified_edges.append({"source_paper_id": source_paper_id, "target_paper_id": target_id, "reason": "No provider-exposed citation edge matched this internal paper pair."})
        record["verified_edges"] = verified_edges
        record["unverified_internal_edges"] = unverified_edges
        if verified_edges:
            record["status"] = "passed"
            record["confidence_level"] = "high"
            record["checks"] = [f"Verified {len(verified_edges)} internal citation graph edge(s) using provider-exposed references/citations."]
        elif record.get("referenced_external_ids") or record.get("citing_external_ids") or record.get("referenced_titles") or record.get("citing_titles"):
            record["status"] = "unknown"
            record["confidence_level"] = "medium"
            record["checks"] = ["Provider graph data was available, but no internal paper-to-paper edge was confirmed."]
        else:
            record["status"] = "unknown"
            record["confidence_level"] = "low"
            record["checks"] = ["Provider metadata was found, but references/citations were not exposed for this record."]
        return record

    @staticmethod
    def paper_identity_index(papers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for paper in papers:
            paper_id = str(paper.get("paper_id") or "")
            if not paper_id:
                continue
            identifiers = []
            doi = str(paper.get("doi") or "").strip()
            arxiv_id = str(paper.get("arxiv_id") or "").strip()
            url = str(paper.get("url") or "").strip()
            if doi:
                identifiers.extend([doi, f"https://doi.org/{doi}"])
            if arxiv_id:
                identifiers.extend([arxiv_id, f"ARXIV:{arxiv_id}"])
            if url:
                identifiers.append(url)
            index[paper_id] = {
                "title": str(paper.get("title") or ""),
                "identifiers": list(dict.fromkeys(identifiers)),
            }
        return index

    @staticmethod
    def title_in_graph(title: str, candidate_titles: list[str]) -> bool:
        if not title:
            return False
        return any(ClaimVerifier.title_similarity(title, candidate) >= 0.85 for candidate in candidate_titles)

    def numeric_table_checks(self, evidence_items: list[dict[str, Any]], paper_tables_path: Path) -> list[dict[str, Any]]:
        numeric_claims = [
            item for item in evidence_items if self.extract_numbers(str(item.get("claim") or item.get("evidence_text") or ""))
        ]
        if not numeric_claims:
            return [
                {
                    "evidence_id": "",
                    "status": "skipped",
                    "checks": ["No numeric claims were found in evidence_store.jsonl."],
                }
            ]
        if not paper_tables_path.exists():
            return [
                {
                    "evidence_id": str(item.get("evidence_id") or ""),
                    "paper_id": str(item.get("paper_id") or ""),
                    "status": "warning",
                    "numbers": self.extract_numbers(str(item.get("claim") or item.get("evidence_text") or "")),
                    "checks": ["paper_tables.jsonl is missing; numeric claim could not be checked against table candidates."],
                }
                for item in numeric_claims
            ]
        table_rows = self.read_jsonl(paper_tables_path)
        tables_by_paper: dict[str, list[dict[str, Any]]] = {}
        for table in table_rows:
            tables_by_paper.setdefault(str(table.get("paper_id") or ""), []).append(table)

        checks: list[dict[str, Any]] = []
        for item in numeric_claims:
            paper_id = str(item.get("paper_id") or "")
            claim_text = str(item.get("claim") or item.get("evidence_text") or "")
            numbers = self.extract_numbers(claim_text)
            candidate_tables = tables_by_paper.get(paper_id, [])
            matched_tables = []
            for table in candidate_tables:
                table_text = str(table.get("text") or "")
                if all(number in table_text for number in numbers):
                    matched_tables.append(str(table.get("table_id") or ""))
            status = "passed" if matched_tables else "warning"
            checks.append(
                {
                    "evidence_id": str(item.get("evidence_id") or ""),
                    "paper_id": paper_id,
                    "status": status,
                    "numbers": numbers,
                    "matched_table_ids": matched_tables,
                    "checks": [
                        "All numeric strings were found in at least one table candidate."
                        if matched_tables
                        else "Numeric strings were not found together in extracted table candidates."
                    ],
                    "note": "This validates string presence in table candidates, not metric correctness.",
                }
            )
        return checks

    def contradiction_checks(self, evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        comparable: list[dict[str, Any]] = []
        for item in evidence_items:
            claim = str(item.get("claim") or "")
            normalized = self.normalize_claim_for_contradiction(claim)
            if normalized["polarity"] != "neutral":
                comparable.append({**item, "normalized_claim": normalized})
        checks: list[dict[str, Any]] = []
        for index, left in enumerate(comparable):
            for right in comparable[index + 1 :]:
                left_normalized = left["normalized_claim"]
                right_normalized = right["normalized_claim"]
                comparison = self.compare_normalized_claims(left_normalized, right_normalized)
                if not comparison["same_scope"]:
                    continue
                if left_normalized["polarity"] == right_normalized["polarity"]:
                    continue
                checks.append(
                    {
                        "status": "candidate",
                        "left_evidence_id": str(left.get("evidence_id") or ""),
                        "right_evidence_id": str(right.get("evidence_id") or ""),
                        "left_paper_id": str(left.get("paper_id") or ""),
                        "right_paper_id": str(right.get("paper_id") or ""),
                        "left_polarity": left_normalized["polarity"],
                        "right_polarity": right_normalized["polarity"],
                        "topic_key": comparison["topic_key"],
                        "topic_overlap": comparison["topic_overlap"],
                        "semantic_similarity": comparison["semantic_similarity"],
                        "shared_metrics": comparison["shared_metrics"],
                        "shared_entities": comparison["shared_entities"],
                        "left_normalized_claim": left_normalized,
                        "right_normalized_claim": right_normalized,
                        "contradiction_type": comparison["contradiction_type"],
                        "checks": [
                            "Claims have opposing normalized semantic polarity within the same method/metric/topic scope and should be manually reviewed."
                        ],
                    }
                )
        if not checks:
            return [
                {
                    "status": "passed",
                    "checks": ["No semantic contradiction candidates were detected."],
                }
            ]
        return checks

    @staticmethod
    def extract_numbers(text: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", text)))

    @staticmethod
    def claim_polarity(claim: str) -> str:
        normalized = ClaimVerifier.normalize_claim_for_contradiction(claim)
        return "" if normalized["polarity"] == "neutral" else str(normalized["polarity"])

    @staticmethod
    def normalize_claim_for_contradiction(claim: str) -> dict[str, Any]:
        lower = claim.lower()
        tokens = re.findall(r"[a-z0-9]+", lower)
        normalized_tokens = [ClaimVerifier.normalize_semantic_token(token) for token in tokens]
        canonical_terms = list(dict.fromkeys(token for token in normalized_tokens if token and token not in ClaimVerifier.semantic_stopwords()))
        entities = ClaimVerifier.extract_semantic_entities(lower, canonical_terms)
        metrics = ClaimVerifier.extract_semantic_metrics(lower, canonical_terms)
        positive_terms = ClaimVerifier.matched_terms(
            lower,
            [
                "outperform",
                "outperforms",
                "improve",
                "improves",
                "improved",
                "enhance",
                "enhances",
                "better",
                "superior",
                "increase",
                "increases",
                "achieve",
                "achieves",
                "higher",
                "more accurate",
                "state of the art",
                "sota",
            ],
        )
        negative_terms = ClaimVerifier.matched_terms(
            lower,
            [
                "underperform",
                "underperforms",
                "degrade",
                "degrades",
                "worse",
                "inferior",
                "decrease",
                "decreases",
                "fail",
                "fails",
                "limited",
                "limitation",
                "lower",
                "less accurate",
                "does not improve",
                "do not improve",
                "doesn't improve",
                "cannot improve",
                "not improve",
            ],
        )
        negated_positive = bool(re.search(r"\b(no|not|never|without|cannot|can't|doesn'?t|do not|does not)\b.{0,25}\b(improve|outperform|enhance|increase|achieve)", lower))
        positive = bool(positive_terms) and not negated_positive
        negative = bool(negative_terms) or negated_positive
        if positive and not negative:
            polarity = "positive"
        elif negative and not positive:
            polarity = "negative"
        elif positive and negative:
            polarity = "mixed"
        else:
            polarity = "neutral"
        topic_terms = ClaimVerifier.topic_terms(canonical_terms, entities, metrics)
        return {
            "polarity": polarity,
            "canonical_terms": canonical_terms,
            "topic_terms": topic_terms,
            "entities": entities,
            "metrics": metrics,
            "positive_markers": positive_terms,
            "negative_markers": negative_terms,
            "negated_positive": negated_positive,
            "numbers": ClaimVerifier.extract_numbers(claim),
        }

    @staticmethod
    def normalize_semantic_token(token: str) -> str:
        synonyms = {
            "enhance": "improve",
            "enhances": "improve",
            "enhanced": "improve",
            "improves": "improve",
            "improved": "improve",
            "outperforms": "outperform",
            "outperformed": "outperform",
            "achieves": "achieve",
            "achieved": "achieve",
            "degrades": "degrade",
            "degraded": "degrade",
            "reduces": "decrease",
            "reduced": "decrease",
            "decreases": "decrease",
            "decreased": "decrease",
            "underperforms": "underperform",
            "underperformed": "underperform",
            "accuracy": "quality",
            "fidelity": "quality",
            "performance": "quality",
            "reconstruction": "reconstruction",
            "rendering": "rendering",
            "scene": "scene",
            "scenes": "scene",
            "datasets": "dataset",
            "benchmarks": "benchmark",
            "methods": "method",
            "models": "model",
            "approaches": "approach",
        }
        return synonyms.get(token, token)

    @staticmethod
    def semantic_stopwords() -> set[str]:
        return {
            "we",
            "the",
            "a",
            "an",
            "and",
            "or",
            "to",
            "of",
            "in",
            "on",
            "for",
            "with",
            "by",
            "our",
            "this",
            "that",
            "paper",
            "result",
            "results",
            "show",
            "shows",
            "using",
            "use",
            "than",
            "over",
            "across",
            "from",
            "as",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
        }

    @staticmethod
    def matched_terms(text: str, terms: list[str]) -> list[str]:
        matches = []
        for term in terms:
            pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
            if re.search(pattern, text):
                matches.append(term)
        return matches

    @staticmethod
    def extract_semantic_entities(text: str, canonical_terms: list[str]) -> list[str]:
        entities = []
        known = ["banf", "nerf", "instant ngp", "instant-ngp", "mip nerf", "mip-nerf", "gaussian splatting"]
        for entity in known:
            if entity in text:
                entities.append(entity.replace(" ", "_").replace("-", "_"))
        uppercase_like = re.findall(r"\b[A-Z][A-Za-z0-9-]{2,}\b", text)
        entities.extend(item.lower().replace("-", "_") for item in uppercase_like)
        if "neural" in canonical_terms and "field" in canonical_terms:
            entities.append("neural_field")
        return list(dict.fromkeys(entities))

    @staticmethod
    def extract_semantic_metrics(text: str, canonical_terms: list[str]) -> list[str]:
        metrics = []
        metric_patterns = {
            "reconstruction_quality": ["reconstruction quality", "image quality", "image fidelity", "visual quality"],
            "accuracy": ["accuracy", "accurate"],
            "speed": ["speed", "runtime", "latency", "efficiency", "faster", "slower"],
            "memory": ["memory", "storage"],
            "psnr": ["psnr"],
            "ssim": ["ssim"],
            "lpips": ["lpips"],
        }
        for metric, patterns in metric_patterns.items():
            if any(pattern in text for pattern in patterns):
                metrics.append(metric)
        if "reconstruction" in canonical_terms and "quality" in canonical_terms:
            metrics.append("reconstruction_quality")
        if "rendering" in canonical_terms and "quality" in canonical_terms:
            metrics.append("reconstruction_quality")
        return list(dict.fromkeys(metrics))

    @staticmethod
    def topic_terms(canonical_terms: list[str], entities: list[str], metrics: list[str]) -> list[str]:
        action_terms = {
            "improve",
            "outperform",
            "achieve",
            "better",
            "superior",
            "increase",
            "higher",
            "underperform",
            "worse",
            "lower",
            "inferior",
            "decrease",
            "fail",
            "limited",
            "degrade",
        }
        terms = [term for term in canonical_terms if term not in action_terms and not term.isdigit()]
        return list(dict.fromkeys(entities + metrics + terms))[:12]

    @staticmethod
    def compare_normalized_claims(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        left_topics = set(left.get("topic_terms") or [])
        right_topics = set(right.get("topic_terms") or [])
        left_metrics = set(left.get("metrics") or [])
        right_metrics = set(right.get("metrics") or [])
        left_entities = set(left.get("entities") or [])
        right_entities = set(right.get("entities") or [])
        shared_metrics = sorted(left_metrics & right_metrics)
        shared_entities = sorted(left_entities & right_entities)
        topic_overlap = ClaimVerifier.topic_overlap(" ".join(left_topics), " ".join(right_topics))
        union = left_topics | right_topics
        semantic_similarity = len(left_topics & right_topics) / len(union) if union else 0.0
        same_scope = bool(shared_metrics and (shared_entities or topic_overlap >= 0.35))
        if not same_scope:
            same_scope = bool(shared_entities and topic_overlap >= 0.45)
        contradiction_type = "opposing_metric_claim" if shared_metrics else "opposing_topic_claim"
        topic_key = " ".join(sorted((left_topics & right_topics) or left_topics or right_topics)[:8])
        return {
            "same_scope": same_scope,
            "topic_overlap": round(topic_overlap, 4),
            "semantic_similarity": round(semantic_similarity, 4),
            "shared_metrics": shared_metrics,
            "shared_entities": shared_entities,
            "contradiction_type": contradiction_type,
            "topic_key": topic_key,
        }

    @staticmethod
    def topic_key(claim: str) -> str:
        tokens = re.findall(r"[a-z0-9]+", claim.lower())
        stopwords = {
            "we",
            "the",
            "a",
            "an",
            "and",
            "or",
            "to",
            "of",
            "in",
            "on",
            "for",
            "with",
            "by",
            "our",
            "method",
            "model",
            "paper",
            "result",
            "results",
            "achieve",
            "outperform",
            "improve",
            "higher",
            "better",
            "superior",
            "underperform",
            "worse",
            "lower",
            "inferior",
            "decrease",
            "fail",
            "limited",
        }
        kept = [token for token in tokens if token not in stopwords and not token.isdigit()]
        return " ".join(kept[:6])

    @staticmethod
    def topic_overlap(left: str, right: str) -> float:
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))

    def authority_checks_for_paper(
        self,
        paper: dict[str, Any],
        cache: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        paper_id = str(paper.get("paper_id") or "")
        doi = str(paper.get("doi") or "").strip()
        arxiv_id = str(paper.get("arxiv_id") or "").strip()
        title = str(paper.get("title") or "").strip()
        checks: list[dict[str, Any]] = []
        if doi:
            checks.append(
                self.cached_authority_check(
                    cache=cache,
                    provider="crossref",
                    identifier=doi,
                    check=lambda: self.check_crossref_doi(paper_id=paper_id, doi=doi, title=title),
                )
            )
            checks.append(
                self.cached_authority_check(
                    cache=cache,
                    provider="openalex",
                    identifier=doi,
                    check=lambda: self.check_openalex_doi(paper_id=paper_id, doi=doi, title=title),
                )
            )
        if arxiv_id:
            checks.append(
                self.cached_authority_check(
                    cache=cache,
                    provider="arxiv",
                    identifier=arxiv_id,
                    check=lambda: self.check_arxiv_id(paper_id=paper_id, arxiv_id=arxiv_id, title=title),
                )
            )
        if title:
            checks.append(
                self.cached_authority_check(
                    cache=cache,
                    provider="semantic_scholar",
                    identifier=title,
                    check=lambda: self.check_semantic_scholar_title(paper_id=paper_id, title=title),
                )
            )
        if not checks:
            checks.append(
                {
                    "paper_id": paper_id,
                    "provider": "",
                    "status": "warning",
                    "authority_confidence": 0.0,
                    "confidence_level": "none",
                    "cache_hit": False,
                    "checks": ["No DOI, arXiv ID, or title available for authority checks."],
                }
            )
        return checks

    def cached_authority_check(
        self,
        cache: dict[str, Any] | None,
        provider: str,
        identifier: str,
        check: Any,
    ) -> dict[str, Any]:
        cache_key = self.authority_cache_key(provider, identifier)
        if cache is not None and cache_key in cache and isinstance(cache[cache_key], dict):
            cached = dict(cache[cache_key])
            cached["cache_hit"] = True
            return cached
        result = dict(check())
        result.setdefault("provider", provider)
        result.setdefault("identifier", identifier)
        result.setdefault("cache_hit", False)
        result = self.apply_authority_policy(result)
        if cache is not None and result.get("status") != "failed":
            cache[cache_key] = {**result, "cache_hit": False}
        return result

    def check_crossref_doi(self, paper_id: str, doi: str, title: str) -> dict[str, Any]:
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
        payload, error = self.read_json_url(url)
        if error:
            return self.authority_error(paper_id, "crossref", doi, error)
        message = payload.get("message") if isinstance(payload, dict) else {}
        candidate_title = ""
        if isinstance(message, dict):
            titles = message.get("title")
            if isinstance(titles, list) and titles:
                candidate_title = str(titles[0])
        return self.authority_match(
            paper_id=paper_id,
            provider="crossref",
            identifier=doi,
            expected_title=title,
            candidate_title=candidate_title,
        )

    def check_openalex_doi(self, paper_id: str, doi: str, title: str) -> dict[str, Any]:
        url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi)}"
        payload, error = self.read_json_url(url)
        if error:
            return self.authority_error(paper_id, "openalex", doi, error)
        candidate_title = str(payload.get("title") or "") if isinstance(payload, dict) else ""
        return self.authority_match(
            paper_id=paper_id,
            provider="openalex",
            identifier=doi,
            expected_title=title,
            candidate_title=candidate_title,
        )

    def check_arxiv_id(self, paper_id: str, arxiv_id: str, title: str) -> dict[str, Any]:
        url = (
            "https://export.arxiv.org/api/query?"
            + urllib.parse.urlencode({"id_list": arxiv_id, "max_results": 1})
        )
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AutoResearchVerifier/0.1"})
            with urllib.request.urlopen(request, timeout=20) as response:
                text = response.read().decode("utf-8", errors="ignore")
            title_match = re.search(r"<title>(.*?)</title>", text, flags=re.DOTALL)
            candidate_title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
            if candidate_title.lower() == "arxiv query":
                candidate_title = ""
        except Exception as exc:  # noqa: BLE001
            return self.authority_error(paper_id, "arxiv", arxiv_id, str(exc))
        return self.authority_match(
            paper_id=paper_id,
            provider="arxiv",
            identifier=arxiv_id,
            expected_title=title,
            candidate_title=candidate_title,
        )

    def check_semantic_scholar_title(self, paper_id: str, title: str) -> dict[str, Any]:
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search?"
            + urllib.parse.urlencode({"query": title, "limit": 1, "fields": "title,year,url"})
        )
        payload, error = self.read_json_url(url)
        if error:
            return self.authority_error(paper_id, "semantic_scholar", title, error)
        candidate_title = ""
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                candidate_title = str(data[0].get("title") or "")
        return self.authority_match(
            paper_id=paper_id,
            provider="semantic_scholar",
            identifier=title,
            expected_title=title,
            candidate_title=candidate_title,
        )

    @staticmethod
    def authority_match(
        paper_id: str,
        provider: str,
        identifier: str,
        expected_title: str,
        candidate_title: str,
    ) -> dict[str, Any]:
        if not candidate_title:
            return ClaimVerifier.apply_authority_policy(
                {
                    "paper_id": paper_id,
                    "provider": provider,
                    "identifier": identifier,
                    "status": "warning",
                    "checks": ["Provider responded, but no title was found."],
                    "candidate_title": "",
                    "title_similarity": 0.0,
                }
            )
        similarity = ClaimVerifier.title_similarity(expected_title, candidate_title)
        status = "passed" if similarity >= 0.75 or not expected_title else "warning"
        return ClaimVerifier.apply_authority_policy(
            {
                "paper_id": paper_id,
                "provider": provider,
                "identifier": identifier,
                "status": status,
                "checks": [f"Title similarity: {similarity:.3f}"],
                "candidate_title": candidate_title,
                "title_similarity": similarity,
            }
        )

    @staticmethod
    def authority_error(paper_id: str, provider: str, identifier: str, error: str) -> dict[str, Any]:
        return ClaimVerifier.apply_authority_policy(
            {
                "paper_id": paper_id,
                "provider": provider,
                "identifier": identifier,
                "status": "failed",
                "checks": ["Authority provider request failed; this is not evidence that the paper is nonexistent."],
                "error": error,
            }
        )

    @staticmethod
    def apply_authority_policy(result: dict[str, Any]) -> dict[str, Any]:
        provider = str(result.get("provider") or "")
        provider_weight = {
            "crossref": 0.95,
            "openalex": 0.9,
            "arxiv": 0.95,
            "semantic_scholar": 0.8,
        }.get(provider, 0.5)
        if result.get("status") == "failed":
            confidence = 0.0
        elif result.get("status") == "skipped":
            confidence = 0.0
        else:
            similarity = float(result.get("title_similarity", 0.0) or 0.0)
            confidence = provider_weight * similarity
            if not result.get("candidate_title") and result.get("status") == "warning":
                confidence = 0.25 * provider_weight
        if confidence >= 0.75:
            level = "high"
        elif confidence >= 0.45:
            level = "medium"
        elif confidence > 0.0:
            level = "low"
        else:
            level = "none"
        result["authority_confidence"] = round(confidence, 4)
        result["confidence_level"] = level
        result["provider_weight"] = provider_weight
        result.setdefault("cache_hit", False)
        result["match_policy"] = "provider_weight * title_similarity"
        return result

    @staticmethod
    def authority_cache_key(provider: str, identifier: str) -> str:
        normalized = re.sub(r"\s+", " ", identifier.strip().lower())
        return f"{provider}:{normalized}"

    @staticmethod
    def read_authority_cache(cache_path: Path | None) -> dict[str, Any]:
        if not cache_path or not cache_path.exists():
            return {}
        try:
            value = json.loads(cache_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def write_authority_cache(cache_path: Path | None, cache: dict[str, Any]) -> None:
        if not cache_path:
            return
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def title_similarity(left: str, right: str) -> float:
        left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
        right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    @staticmethod
    def read_json_url(url: str) -> tuple[dict[str, Any], str]:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AutoResearchVerifier/0.1"})
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {}, ""
        except Exception as exc:  # noqa: BLE001
            return {}, str(exc)

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
    def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def render_report(
        result_payload: dict[str, Any],
        checks: list[ClaimVerification],
        unsupported: list[dict[str, Any]],
    ) -> str:
        lines = [
            "# Verification Report",
            "",
            "## Summary",
            "",
            f"- verification_passed: {str(result_payload['verification_passed']).lower()}",
            f"- publication_ready: {str(result_payload['publication_ready']).lower()}",
            f"- checked_claim_count: {result_payload['checked_claim_count']}",
            f"- unsupported_claim_count: {result_payload['unsupported_claim_count']}",
            f"- abstract_only_warning_count: {result_payload['abstract_only_warning_count']}",
            f"- citation_check_count: {result_payload['citation_check_count']}",
            f"- citation_warning_count: {result_payload['citation_warning_count']}",
            f"- citation_authority_check_count: {result_payload['citation_authority_check_count']}",
            f"- citation_authority_warning_count: {result_payload['citation_authority_warning_count']}",
            f"- citation_authority_failed_count: {result_payload['citation_authority_failed_count']}",
            f"- citation_authority_low_confidence_count: {result_payload['citation_authority_low_confidence_count']}",
            f"- citation_authority_cache_hit_count: {result_payload['citation_authority_cache_hit_count']}",
            f"- citation_graph_check_count: {result_payload['citation_graph_check_count']}",
            f"- citation_graph_edge_count: {result_payload['citation_graph_edge_count']}",
            f"- citation_graph_warning_count: {result_payload['citation_graph_warning_count']}",
            f"- citation_graph_unknown_count: {result_payload['citation_graph_unknown_count']}",
            f"- citation_graph_cache_hit_count: {result_payload['citation_graph_cache_hit_count']}",
            f"- authority_checks_enabled: {str(result_payload['authority_checks_enabled']).lower()}",
            f"- numeric_table_check_count: {result_payload['numeric_table_check_count']}",
            f"- numeric_table_warning_count: {result_payload['numeric_table_warning_count']}",
            f"- contradiction_check_count: {result_payload['contradiction_check_count']}",
            f"- contradiction_candidate_count: {result_payload['contradiction_candidate_count']}",
            "",
            "## Claim Checks",
            "",
        ]
        if not checks:
            lines.append("- No claim checks were produced.")
        for check in checks:
            lines.append(f"- `{check.evidence_id}`: {check.status} ({check.support_level})")
            if check.issues:
                for issue in check.issues:
                    lines.append(f"  - {issue}")

        lines.extend(["", "## Unsupported Claims", ""])
        if not unsupported:
            lines.append("- None.")
        for item in unsupported:
            evidence_id = item.get("evidence_id") or "(missing evidence id)"
            lines.append(f"- `{evidence_id}`: {item.get('issue')}")

        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                "- `verification_passed=true` means evidence IDs and source pointers are traceable.",
                "- `publication_ready=false` means additional full-text verification is still needed.",
                "- This stage checks traceability and source support structure, not external scientific truth.",
            ]
        )
        return "\n".join(lines) + "\n"
