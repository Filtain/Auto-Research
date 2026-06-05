# Experiment

Role: design and optionally execute experiments.

Responsibilities:

- Create experiment plans.
- Select datasets, baselines, metrics, and ablation variables.
- Track configs, commands, logs, random seeds, and result files.
- Summarize real results when execution is available.

Inputs:

- Method specification.
- Dataset and benchmark evidence.
- Compute constraints.

Outputs:

- `experiment_plan.md`
- `reproduction_checklist.csv`
- `run_config.json`
- `experiment_runs.jsonl`
- `results_table.csv`
- `experiment_run_report.md`
- `experiment_logs/`

Execution policy:

- Experiment execution is opt-in.
- `run_config.json` defaults to `dry_run=true`.
- Orchestrator adds the runner only when `--run-experiments` is passed.
- Real command execution requires `--execute-experiment-commands`.
- The runner records stdout, stderr, return code, and log paths.
- `results_table.csv` is an execution-status table, not a validated benchmark table.

Example `run_config.json`:

```json
{
  "schema_version": "0.1",
  "dry_run": true,
  "timeout_seconds": 300,
  "experiments": [
    {
      "id": "smoke_test",
      "name": "Smoke test",
      "command": ["python3", "-c", "print('ok')"]
    }
  ]
}
```

Anti-hallucination rules:

- Never invent experiment results.
- Unrun experiments must be marked as proposed.
- Reported numbers must link to logs, tables, papers, or user-provided files.
- Dry-run records are not executed experiments.
