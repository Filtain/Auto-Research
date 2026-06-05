import json
import tempfile
import unittest
from pathlib import Path

from verification.src.verifier import ClaimVerifier


class ClaimVerifierTests(unittest.TestCase):
    def test_verifies_traceable_abstract_only_claim_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            evidence = {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "paper_title": "A Retrieved Paper",
                "claim": "We propose a neural field method.",
                "claim_type": "author_claim",
                "evidence_text": "We propose a neural field method.",
                "source_type": "paper",
                "source_location": {
                    "section": "abstract",
                    "page": None,
                    "url": "https://arxiv.org/abs/1",
                    "read_source": "abstract_metadata_only",
                },
                "support_level": "abstract_metadata_only",
                "full_text_available": False,
                "read_source": "abstract_metadata_only",
                "confidence": "medium",
            }
            source_map = {
                "papers": {"p1": {"paper_title": "A Retrieved Paper"}},
                "evidence_sources": {"p1:claim:1": {"paper_id": "p1"}},
            }
            synthesis_summary = {
                "paper_evidence": [
                    {
                        "paper_id": "p1",
                        "evidence_ids": ["p1:claim:1"],
                    }
                ]
            }
            (output_dir / "evidence_store.jsonl").write_text(
                json.dumps(evidence, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (output_dir / "source_map.json").write_text(
                json.dumps(source_map, ensure_ascii=False),
                encoding="utf-8",
            )
            (output_dir / "synthesis_summary.json").write_text(
                json.dumps(synthesis_summary, ensure_ascii=False),
                encoding="utf-8",
            )
            (output_dir / "report.md").write_text(
                "- [p1:claim:1] We propose a neural field method.\n",
                encoding="utf-8",
            )

            result = ClaimVerifier().verify_claims(task_input={}, output_dir=output_dir)

            self.assertTrue(Path(result.verification_report_md).exists())
            self.assertTrue(Path(result.verification_result_json).exists())
            self.assertTrue(Path(result.claim_verification_jsonl).exists())
            self.assertTrue(Path(result.unsupported_claims_jsonl).exists())
            self.assertTrue(Path(result.citation_checks_jsonl).exists())
            self.assertTrue(Path(result.citation_authority_checks_jsonl).exists())
            self.assertTrue(Path(result.citation_graph_checks_jsonl).exists())
            self.assertTrue(Path(result.numeric_table_checks_jsonl).exists())
            self.assertTrue(Path(result.contradiction_checks_jsonl).exists())
            self.assertTrue(result.verification_passed)
            self.assertFalse(result.publication_ready)
            self.assertEqual(result.checked_claim_count, 1)
            self.assertEqual(result.unsupported_claim_count, 0)
            self.assertEqual(result.abstract_only_warning_count, 1)
            self.assertEqual(result.citation_check_count, 1)
            self.assertEqual(result.citation_authority_check_count, 1)
            self.assertEqual(result.numeric_table_check_count, 1)
            self.assertEqual(result.contradiction_check_count, 1)
            authority = json.loads((output_dir / "citation_authority_checks.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(authority["status"], "skipped")
            graph = json.loads((output_dir / "citation_graph_checks.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(graph["status"], "skipped")

    def test_citation_graph_checks_verify_internal_reference_edge_with_mocked_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            cache_path = output_dir / "authority_cache.json"
            (output_dir / "papers_raw.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "paper_id": "p1",
                                "title": "Source Paper",
                                "doi": "10.1234/source",
                                "arxiv_id": "",
                                "url": "https://doi.org/10.1234/source",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "paper_id": "p2",
                                "title": "Target Paper",
                                "doi": "10.1234/target",
                                "arxiv_id": "",
                                "url": "https://doi.org/10.1234/target",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            verifier = ClaimVerifier()
            verifier.fetch_openalex_graph_record = lambda paper_id, doi, title: {  # type: ignore[method-assign]
                "provider": "openalex",
                "status": "passed",
                "external_id": f"https://openalex.org/{paper_id}",
                "doi": doi,
                "title": title,
                "referenced_external_ids": ["https://doi.org/10.1234/target"] if paper_id == "p1" else [],
                "reference_count": 1 if paper_id == "p1" else 0,
                "checks": ["mocked"],
            }
            verifier.fetch_semantic_scholar_graph_record = lambda paper_id, doi, arxiv_id, title: {  # type: ignore[method-assign]
                "provider": "semantic_scholar",
                "status": "skipped",
                "checks": ["mocked skip"],
            }

            checks = verifier.citation_graph_checks(
                output_dir / "papers_raw.jsonl",
                enabled=True,
                cache_path=cache_path,
            )

            source_check = next(check for check in checks if check["paper_id"] == "p1")
            self.assertEqual(source_check["status"], "passed")
            self.assertEqual(source_check["confidence_level"], "high")
            self.assertEqual(source_check["verified_edges"][0]["direction"], "references")
            self.assertEqual(source_check["verified_edges"][0]["target_paper_id"], "p2")
            self.assertTrue(cache_path.exists())

    def test_citation_graph_checks_use_cache_for_provider_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            cache_path = output_dir / "authority_cache.json"
            (output_dir / "papers_raw.jsonl").write_text(
                json.dumps(
                    {
                        "paper_id": "p1",
                        "title": "Source Paper",
                        "doi": "10.1234/source",
                        "arxiv_id": "",
                        "url": "https://doi.org/10.1234/source",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            call_count = {"openalex": 0}
            verifier = ClaimVerifier()

            def fake_openalex(paper_id, doi, title):
                call_count["openalex"] += 1
                return {
                    "provider": "openalex",
                    "status": "passed",
                    "external_id": "https://openalex.org/W1",
                    "doi": doi,
                    "title": title,
                    "referenced_external_ids": [],
                    "reference_count": 0,
                    "checks": ["mocked"],
                }

            verifier.fetch_openalex_graph_record = fake_openalex  # type: ignore[method-assign]
            verifier.fetch_semantic_scholar_graph_record = lambda paper_id, doi, arxiv_id, title: {  # type: ignore[method-assign]
                "provider": "semantic_scholar",
                "status": "skipped",
                "checks": ["mocked skip"],
            }

            first = verifier.citation_graph_checks(output_dir / "papers_raw.jsonl", enabled=True, cache_path=cache_path)
            second = verifier.citation_graph_checks(output_dir / "papers_raw.jsonl", enabled=True, cache_path=cache_path)

            self.assertEqual(call_count["openalex"], 1)
            self.assertFalse(first[0]["cache_hit"])
            self.assertTrue(second[0]["cache_hit"])

    def test_authority_checks_can_be_enabled_with_mocked_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "papers_raw.jsonl").write_text(
                json.dumps(
                    {
                        "paper_id": "p1",
                        "title": "A Retrieved Paper",
                        "doi": "10.1234/example",
                        "arxiv_id": "",
                        "url": "https://example.com",
                        "source": "crossref",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            verifier = ClaimVerifier()
            verifier.check_crossref_doi = lambda paper_id, doi, title: {  # type: ignore[method-assign]
                "paper_id": paper_id,
                "provider": "crossref",
                "identifier": doi,
                "status": "passed",
                "checks": ["mocked"],
                "candidate_title": title,
                "title_similarity": 1.0,
            }
            verifier.check_openalex_doi = lambda paper_id, doi, title: {  # type: ignore[method-assign]
                "paper_id": paper_id,
                "provider": "openalex",
                "identifier": doi,
                "status": "passed",
                "checks": ["mocked"],
                "candidate_title": title,
                "title_similarity": 1.0,
            }
            verifier.check_semantic_scholar_title = lambda paper_id, title: {  # type: ignore[method-assign]
                "paper_id": paper_id,
                "provider": "semantic_scholar",
                "identifier": title,
                "status": "passed",
                "checks": ["mocked"],
                "candidate_title": title,
                "title_similarity": 1.0,
            }

            checks = verifier.authority_cross_checks(output_dir / "papers_raw.jsonl", enabled=True)

            self.assertEqual(len(checks), 3)
            self.assertTrue(all(check["status"] == "passed" for check in checks))
            self.assertTrue(all("authority_confidence" in check for check in checks))
            self.assertTrue(all(check["confidence_level"] == "high" for check in checks))

    def test_authority_checks_use_cache_and_do_not_repeat_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            cache_path = output_dir / "authority_cache.json"
            (output_dir / "papers_raw.jsonl").write_text(
                json.dumps(
                    {
                        "paper_id": "p1",
                        "title": "A Retrieved Paper",
                        "doi": "10.1234/example",
                        "arxiv_id": "",
                        "url": "https://example.com",
                        "source": "crossref",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            call_count = {"crossref": 0}
            verifier = ClaimVerifier()

            def fake_crossref(paper_id, doi, title):
                call_count["crossref"] += 1
                return {
                    "paper_id": paper_id,
                    "provider": "crossref",
                    "identifier": doi,
                    "status": "passed",
                    "checks": ["mocked"],
                    "candidate_title": title,
                    "title_similarity": 1.0,
                }

            verifier.check_crossref_doi = fake_crossref  # type: ignore[method-assign]
            verifier.check_openalex_doi = lambda paper_id, doi, title: {  # type: ignore[method-assign]
                "paper_id": paper_id,
                "provider": "openalex",
                "identifier": doi,
                "status": "failed",
                "checks": ["mocked failure"],
            }
            verifier.check_semantic_scholar_title = lambda paper_id, title: {  # type: ignore[method-assign]
                "paper_id": paper_id,
                "provider": "semantic_scholar",
                "identifier": title,
                "status": "failed",
                "checks": ["mocked failure"],
            }

            first = verifier.authority_cross_checks(output_dir / "papers_raw.jsonl", enabled=True, cache_path=cache_path)
            second = verifier.authority_cross_checks(output_dir / "papers_raw.jsonl", enabled=True, cache_path=cache_path)

            crossref_first = next(check for check in first if check["provider"] == "crossref")
            crossref_second = next(check for check in second if check["provider"] == "crossref")
            self.assertEqual(call_count["crossref"], 1)
            self.assertFalse(crossref_first["cache_hit"])
            self.assertTrue(crossref_second["cache_hit"])
            self.assertEqual(crossref_second["confidence_level"], "high")
            self.assertTrue(cache_path.exists())

    def test_authority_policy_marks_low_confidence_title_match(self) -> None:
        result = ClaimVerifier.authority_match(
            paper_id="p1",
            provider="semantic_scholar",
            identifier="query title",
            expected_title="A Retrieved Paper",
            candidate_title="Completely Different Work",
        )

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["confidence_level"], "none")
        self.assertLess(result["authority_confidence"], 0.45)

    def test_numeric_table_checks_match_numbers_in_table_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            evidence = [
                {
                    "evidence_id": "p1:claim:1",
                    "paper_id": "p1",
                    "claim": "Our method achieves PSNR 31.0 and SSIM 0.91.",
                    "evidence_text": "Our method achieves PSNR 31.0 and SSIM 0.91.",
                }
            ]
            (output_dir / "paper_tables.jsonl").write_text(
                json.dumps(
                    {
                        "paper_id": "p1",
                        "table_id": "t1",
                        "text": "Method PSNR SSIM\nOurs 31.0 0.91",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            checks = ClaimVerifier().numeric_table_checks(evidence, output_dir / "paper_tables.jsonl")

            self.assertEqual(checks[0]["status"], "passed")
            self.assertEqual(checks[0]["matched_table_ids"], ["t1"])

    def test_contradiction_checks_flags_opposing_claims(self) -> None:
        evidence = [
            {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "claim": "BANF improves reconstruction quality on NeRF scenes.",
            },
            {
                "evidence_id": "p2:claim:1",
                "paper_id": "p2",
                "claim": "BANF fails reconstruction quality on NeRF scenes.",
            },
        ]

        checks = ClaimVerifier().contradiction_checks(evidence)

        self.assertEqual(checks[0]["status"], "candidate")
        self.assertEqual(checks[0]["left_evidence_id"], "p1:claim:1")

    def test_contradiction_checks_use_semantic_normalization(self) -> None:
        evidence = [
            {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "claim": "BANF enhances image fidelity for neural field reconstruction.",
            },
            {
                "evidence_id": "p2:claim:1",
                "paper_id": "p2",
                "claim": "BANF does not improve reconstruction quality in NeRF scenes.",
            },
        ]

        checks = ClaimVerifier().contradiction_checks(evidence)

        self.assertEqual(checks[0]["status"], "candidate")
        self.assertEqual(checks[0]["contradiction_type"], "opposing_metric_claim")
        self.assertIn("reconstruction_quality", checks[0]["shared_metrics"])
        self.assertIn("banf", checks[0]["shared_entities"])
        self.assertEqual(checks[0]["left_polarity"], "positive")
        self.assertEqual(checks[0]["right_polarity"], "negative")
        self.assertGreater(checks[0]["semantic_similarity"], 0)

    def test_contradiction_checks_avoid_different_metric_scopes(self) -> None:
        evidence = [
            {
                "evidence_id": "p1:claim:1",
                "paper_id": "p1",
                "claim": "BANF improves reconstruction quality in NeRF scenes.",
            },
            {
                "evidence_id": "p2:claim:1",
                "paper_id": "p2",
                "claim": "BANF decreases memory usage during training.",
            },
        ]

        checks = ClaimVerifier().contradiction_checks(evidence)

        self.assertEqual(checks[0]["status"], "passed")

    def test_missing_referenced_evidence_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "evidence_store.jsonl").write_text("", encoding="utf-8")
            (output_dir / "source_map.json").write_text(
                json.dumps({"evidence_sources": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (output_dir / "synthesis_summary.json").write_text(
                json.dumps({"paper_evidence": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (output_dir / "report.md").write_text(
                "- [missing:claim:1] Unsupported claim.\n",
                encoding="utf-8",
            )

            result = ClaimVerifier().verify_claims(task_input={}, output_dir=output_dir)

            self.assertFalse(result.verification_passed)
            self.assertFalse(result.publication_ready)
            self.assertEqual(result.checked_claim_count, 1)
            self.assertEqual(result.unsupported_claim_count, 1)
            unsupported = (output_dir / "unsupported_claims.jsonl").read_text(encoding="utf-8")
            self.assertIn("missing:claim:1", unsupported)

    def test_missing_required_input_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                ClaimVerifier().verify_claims(task_input={}, output_dir=Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
