# Auto Research

Auto Research is an evidence-grounded literature research workflow for building conservative research reports from papers and other scholarly sources.

It is designed for one practical goal: help a user move from a broad research question to traceable artifacts such as retrieved papers, ranked sources, paper readings, evidence records, synthesis reports, verification reports, and final QA decisions.

The project is intentionally conservative. It does not treat generated text as evidence, and it does not silently promote unsupported claims into final output.

## Why This Project Exists

Typical research-agent demos can retrieve papers and write summaries, but they often make it hard to answer basic quality questions:

- Which source supports this claim?
- Did the system read full text or only an abstract?
- Are numeric claims grounded in extracted tables?
- Are citations structurally valid?
- Do two evidence records contradict each other?
- Should the final report be exported, or should it be blocked?

Auto Research turns these questions into explicit pipeline artifacts and QA checks.

## What It Does

Auto Research can:

- Create a research plan and DAG task graph from a user query.
- Retrieve paper metadata from arXiv, Semantic Scholar, OpenAlex, Crossref, OpenReview, PubMed, GitHub, and local PDFs.
- Rank and triage papers with deterministic rules.
- Read abstracts, metadata, local PDFs, and downloaded PDFs when available.
- Extract layout-aware PDF sections, table candidates, formula candidates, and page/bbox provenance when PyMuPDF is installed.
- Build evidence records with stable evidence IDs and source maps.
- Generate evidence-grounded synthesis reports, timelines, method taxonomies, research-gap candidates, and reproducibility routes.
- Verify evidence traceability, citation metadata, provider-exposed citation graph edges, numeric table strings, and semantic-normalized contradiction candidates.
- Run a strict Final QA gate before export.
- Produce optional comparison matrices, idea candidates, method specs, experiment plans, evaluation reports, rebuttal scaffolds, promotion briefs, and PPT outlines.
- Run artifact-level and dataset-level benchmark evaluation.
- Optionally use an LLM for writing assistance while keeping LLM output separate from source evidence.

## Pipeline

The default workflow is:

```text
User query
  -> Planner
  -> Retriever
  -> Paper Triage
  -> Paper Reader
  -> Evidence DB
  -> Synthesis
  -> Verification
  -> Final QA
```

Optional stages can be added:

```text
Comparison
Idea Generation
Method Design
Experiment Planning / Running
Evaluation
Rebuttal
Promotion
Writer
Benchmark
```

## Installation

Requires Python 3.10+.

```bash
python3 -m pip install -e .
```

Optional PDF layout parsing:

```bash
python3 -m pip install -e ".[pdf]"
```

The core tests and offline demo do not require API keys.

## Quickstart

Run a research workflow:

```bash
python3 -m orchestrator.src.orchestrator \
  'large language model agent evaluation methods' \
  --execute \
  --min-sources 2
```

Outputs are written to:

```text
output/<project_id>/
```

Generate control files only, without executing the DAG:

```bash
python3 -m orchestrator.src.orchestrator \
  '帮我调研一个科研主题的方法脉络，并生成一个 PPT 大纲' \
  --output-format ppt
```

Run with optional external authority checks:

```bash
python3 -m orchestrator.src.orchestrator \
  'scientific literature retrieval and evidence-grounded synthesis' \
  --execute \
  --enable-authority-checks \
  --min-sources 2
```

Run an experiment-planning node in dry-run mode:

```bash
python3 -m orchestrator.src.orchestrator \
  '帮我规划一个研究方法的验证流程' \
  --execute \
  --run-experiments
```

Execute configured experiment commands for real:

```bash
python3 -m orchestrator.src.orchestrator \
  '帮我规划一个研究方法的验证流程' \
  --execute \
  --run-experiments \
  --execute-experiment-commands \
  --experiment-timeout-seconds 300
```

Use optional LLM-assisted writing:

```bash
export OPENAI_API_KEY="your_api_key"
python3 -m orchestrator.src.orchestrator \
  '帮我写一个科研主题的论文综述' \
  --execute \
  --use-llm \
  --llm-provider openai \
  --llm-model gpt-4.1-mini
```

## Offline Demo

Run a deterministic local demo without network access:

```bash
python3 examples/demo/run_demo.py
```

Demo outputs are written to:

```text
output/demo_local_pdf/
```

## Benchmarking

Run artifact-level benchmark evaluation:

```bash
python3 -m orchestrator.src.orchestrator \
  'scientific literature review benchmark' \
  --execute \
  --run-benchmark \
  --benchmark-spec examples/demo/benchmark_spec.json \
  --min-sources 2
```

Run a dataset-level benchmark over completed runs:

```bash
python3 -m benchmark.src.dataset_runner \
  --dataset examples/demo/benchmark_dataset.json \
  --output-dir output/benchmark_dataset_demo
```

## Key Outputs

Common pipeline artifacts include:

- `research_plan.json`: structured plan for the research run.
- `task_graph.json`: DAG tasks and dependencies.
- `papers.csv`: retrieved normalized paper metadata.
- `ranked_papers.csv`: triaged and ranked sources.
- `paper_readings.jsonl`: per-paper reading records.
- `paper_layout_blocks.jsonl`: layout-aware PDF blocks when available.
- `paper_sections.jsonl`: extracted section candidates.
- `paper_tables.jsonl`: table candidates.
- `paper_structured_tables.jsonl`: parsed table candidates.
- `paper_structured_tables.csv`: long-form structured table cells.
- `paper_formulas.jsonl`: formula candidates.
- `evidence_store.jsonl`: traceable evidence records.
- `source_map.json`: evidence-to-source map.
- `report.md`: evidence-grounded synthesis report.
- `verification_report.md`: verification summary.
- `verification_result.json`: machine-readable verification result.
- `citation_graph_checks.jsonl`: provider-exposed citation graph checks.
- `final_qa_report.md`: final export gate report.
- `final_decision.json`: final workflow decision.

Optional stages may also produce:

- `literature_matrix.csv`
- `benchmark_matrix.csv`
- `idea_candidates.md`
- `method_spec.md`
- `ablation_plan.md`
- `experiment_plan.md`
- `evaluation_report.md`
- `rebuttal_plan.md`
- `promotion_brief.md`
- `ppt_outline.md`
- `final_report.md`

## Anti-Hallucination Design

Auto Research follows these rules:

- Missing metadata stays empty.
- Abstract-only evidence is marked as weak.
- Full-text availability is explicit.
- PDF layout, table, and formula outputs are extraction candidates until checked against the original PDF.
- External provider failures are logged as uncertainty, not proof that a paper or citation does not exist.
- Citation graph checks only verify provider-exposed references/citations.
- LLM output is optional writing assistance, not a source of new evidence.
- Final QA can complete the workflow while still denying export.

## What This Project Is Not

Auto Research is not:

- A publication-grade autonomous scientist.
- A replacement for expert literature review.
- A universal citation-truth oracle independent of provider graph coverage.
- A guaranteed PDF table/formula parser.
- A validated scientific metric extractor.
- A substitute for real reviewer comments or human-approved dissemination.

## Tests

Run the full local test suite:

```bash
python3 -m unittest discover -s planner/tests
python3 -m unittest discover -s orchestrator/tests
python3 -m unittest discover -s retriever/tests
python3 -m unittest discover -s paper_triage/tests
python3 -m unittest discover -s paper_reader/tests
python3 -m unittest discover -s evidence_db/tests
python3 -m unittest discover -s synthesis/tests
python3 -m unittest discover -s verification/tests
python3 -m unittest discover -s final_qa/tests
python3 -m unittest discover -s benchmark/tests
python3 -m unittest discover -s comparison/tests
python3 -m unittest discover -s idea_generation/tests
python3 -m unittest discover -s method_design/tests
python3 -m unittest discover -s experiment/tests
python3 -m unittest discover -s evaluation/tests
python3 -m unittest discover -s rebuttal/tests
python3 -m unittest discover -s promotion/tests
python3 -m unittest discover -s writer/tests
python3 -m unittest discover -s llm/tests
```

Current local status:

```text
82 tests passing
```

## Repository Layout

```text
orchestrator/      DAG planning and task execution
planner/           Query and criteria planning
retriever/         Multi-source metadata retrieval
paper_triage/      Ranking and inclusion decisions
paper_reader/      Abstract/PDF reading and layout extraction
evidence_db/       Evidence IDs and source maps
synthesis/         Evidence-grounded reports
verification/      Claim, citation, numeric, and contradiction checks
final_qa/          Final export gate
benchmark/         Artifact and dataset benchmark evaluation
comparison/        Literature and benchmark matrices
experiment/        Experiment planning and controlled execution
writer/            Final report assembly and optional LLM summary
examples/demo/     Offline demo fixture
```

## License

MIT License.
