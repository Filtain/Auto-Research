from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.src.evaluator import ArtifactBenchmark
from evidence_db.src.evidence import EvidenceExtractor
from final_qa.src.final_gate import FinalQAGate
from paper_reader.src.reader import PaperReader
from synthesis.src.synthesizer import FindingsSynthesizer
from verification.src.verifier import ClaimVerifier


def main() -> int:
    output_dir = ROOT / "output" / "demo_local_pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "examples" / "demo" / "ranked_papers.csv", output_dir / "ranked_papers.csv")
    shutil.copyfile(ROOT / "examples" / "demo" / "ranked_papers.csv", output_dir / "papers.csv")

    reader = PaperReader()
    reader.read_core_sources({"ranked_papers_csv": str(output_dir / "ranked_papers.csv")}, output_dir)

    extractor = EvidenceExtractor()
    extractor.extract_evidence({}, output_dir)

    synthesizer = FindingsSynthesizer()
    synthesizer.synthesize_findings({}, output_dir)

    verifier = ClaimVerifier()
    verifier.verify_claims({}, output_dir)

    final_qa = FinalQAGate()
    final_qa.run_final_qa({}, output_dir)

    benchmark = ArtifactBenchmark()
    benchmark.evaluate({"benchmark_spec": str(ROOT / "examples" / "demo" / "benchmark_spec.json")}, output_dir)

    print(f"Demo output written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
