# Benchmark

Artifact-level benchmark layer for Auto Research.

This module evaluates pipeline artifacts instead of only scoring final natural
language answers. It checks:

- retrieval: expected key papers found
- triage: expected papers ranked near the top
- reading: expected sections/tables/formulas extracted
- evidence: claims bound to source-map evidence
- synthesis: required topics and evidence IDs present
- verification: unsupported claims detected or cleared according to policy
- final_qa: export gate matches expected safety policy
- end_to_end: required artifacts exist for a safe run

Outputs:

- `benchmark_report.md`
- `benchmark_scores.json`
- `benchmark_failures.jsonl`
- `benchmark_summary.csv`

Ground-truth specs are optional. Without a spec, the benchmark performs
artifact sanity checks only.

## Dataset Benchmark

For large-scale evaluation, use a dataset JSON that points to completed run
directories and per-sample ground-truth specs:

```json
{
  "dataset_name": "my_benchmark",
  "samples": [
    {
      "sample_id": "case_001",
      "run_dir": "output/case_001",
      "benchmark_spec": "benchmarks/specs/case_001.json",
      "split": "dev",
      "tags": ["retrieval", "qa"]
    }
  ]
}
```

Run:

```bash
python3 -m benchmark.src.dataset_runner \
  --dataset examples/demo/benchmark_dataset.json \
  --output-dir output/benchmark_dataset_demo
```

Dataset outputs:

- `benchmark_dataset_metrics.json`
- `benchmark_dataset_results.jsonl`
- `benchmark_dataset_failures.jsonl`
- `benchmark_dataset_leaderboard.csv`
- `benchmark_dataset_report.md`
