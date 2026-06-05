# Evidence DB

Role: persistent research memory and evidence store.

Responsibilities:

- Store raw files, metadata, chunks, embeddings, citation links, evidence records, and claim mappings.
- Assign stable evidence IDs.
- Provide retrieval for synthesis and verification.

Storage layers:

- Raw storage: PDFs, webpages, code, images.
- Metadata DB: title, authors, year, venue, DOI, keywords, citation count.
- Vector DB: abstract, method, experiment, and result chunks.
- Citation graph: references and citations.

Outputs:

- `evidence_store.jsonl`
- `source_map.json`
- Embedding index.

Anti-hallucination rules:

- Every evidence item must preserve source location.
- Evidence text must be copied or tightly grounded from the source.
- Claims without evidence IDs cannot be promoted to final artifacts.
