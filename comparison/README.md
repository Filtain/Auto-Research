# Comparison

Role: compare papers, methods, experiments, datasets, and results.

Responsibilities:

- Generate literature matrices.
- Compare method categories.
- Compare datasets, metrics, baselines, and reported results.
- Identify agreements, disagreements, and condition-dependent differences.

Inputs:

- Paper reading outputs.
- Evidence records.
- Normalized metadata.

Outputs:

- `literature_matrix.csv`
- `method_comparison.md`
- `experiment_comparison.csv`

Anti-hallucination rules:

- Numeric values must come from source evidence.
- Do not compare papers on fields that were not extracted.
- Missing values must remain empty or marked unknown.
