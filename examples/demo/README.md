# Offline Demo

This demo runs without network access. It uses a small local text fixture as a PDF/text stand-in and writes outputs to:

```text
output/demo_local_pdf/
```

Run:

```bash
python examples/demo/run_demo.py
```

Then run the dataset-level benchmark:

```bash
python3 -m benchmark.src.dataset_runner \
  --dataset examples/demo/benchmark_dataset.json \
  --output-dir output/benchmark_dataset_demo
```

Expected artifacts include:

- `paper_readings.jsonl`
- `paper_sections.jsonl`
- `paper_tables.jsonl`
- `paper_structured_tables.jsonl`
- `paper_structured_tables.csv`
- `paper_formulas.jsonl`
- `evidence_store.jsonl`
- `report.md`
- `verification_report.md`
- `final_qa_report.md`
- `benchmark_report.md`
- `benchmark_scores.json`
- `benchmark_failures.jsonl`
- `benchmark_summary.csv`
- `benchmark_dataset_metrics.json`
- `benchmark_dataset_results.jsonl`
- `benchmark_dataset_failures.jsonl`
- `benchmark_dataset_leaderboard.csv`
- `benchmark_dataset_report.md`

The demo is intentionally small and deterministic. It is for smoke testing the pipeline and artifact benchmark layer, not for scientific evaluation.
