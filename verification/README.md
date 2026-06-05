# Verification

Role: enforce citation, claim, metadata, and contradiction checks.

Responsibilities:

- Check citation existence.
- Check citation support.
- Check metadata consistency.
- Check optional external authority metadata with cache and confidence scoring.
- Check provider-exposed citation graph edges for internal paper-to-paper citation links.
- Check semantic-normalized contradiction candidates across sources.
- Check whether experimental values match source evidence.

Inputs:

- Draft claims.
- Evidence store.
- Source map.
- Paper metadata.

Outputs:

- `verification_report.md`
- `claim_verification.jsonl`
- `unsupported_claims.jsonl`
- `citation_checks.jsonl`
- `citation_authority_checks.jsonl`
- `citation_authority_cache.json`
- `citation_graph_checks.jsonl`
- `numeric_table_checks.jsonl`
- `contradiction_checks.jsonl`

Anti-hallucination rules:

- Unsupported claims must be removed, revised, or marked as hypothesis.
- Final export is blocked when unsupported factual claims remain.
- Verification must be independent from writing.
- External authority provider failures are uncertainty signals, not proof that a paper does not exist.
- Authority confidence is a metadata QA signal, not a judgment of scientific truth.
- Citation graph checks verify provider-exposed references/citations when available; missing graph data is uncertainty, not proof of no citation relation.
- Contradiction checks are review candidates, not automatic proof that a source is wrong.
