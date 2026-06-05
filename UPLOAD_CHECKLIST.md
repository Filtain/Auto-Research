# Upload Checklist

This directory is the cleaned GitHub upload root for Auto Research.

Included:

- Source modules and tests.
- Root `README.md`, `pyproject.toml`, `LICENSE`, and `.gitignore`.
- GitHub Actions workflow under `.github/workflows/`.
- Offline demo files under `examples/demo/`.
- Module READMEs, schemas, prompts, SQL examples, and test fixtures.

Excluded:

- Local run outputs under `output/`.
- Python caches such as `__pycache__/` and `*.pyc`.
- Local working notes such as `ar.md` and `consequence.md`.
- Large local research assets such as PDFs, checkpoints, archives, and logs.

Suggested upload flow:

```bash
cd ATR
git init
git add .
git commit -m "Initial Auto Research release"
```

Quick validation:

```bash
python3 -m unittest discover -s verification/tests
python3 -m unittest discover -s orchestrator/tests
python3 examples/demo/run_demo.py
```
