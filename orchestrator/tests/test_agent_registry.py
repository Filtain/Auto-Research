import unittest

from orchestrator.src.agent_registry import AgentRegistry


class AgentRegistryTests(unittest.TestCase):
    def test_registry_exposes_agent_metadata(self) -> None:
        registry = AgentRegistry()
        search = registry.get("search_sources")
        rank = registry.get("rank_sources")
        reader = registry.get("read_core_sources")
        evidence = registry.get("extract_evidence")
        synthesis = registry.get("synthesize_findings")
        verifier = registry.get("verify_claims")
        final_qa = registry.get("final_qa")
        compare = registry.get("compare_methods")
        ideas = registry.get("generate_ideas")
        method = registry.get("design_method")
        evaluation = registry.get("evaluate_results")
        run_experiments = registry.get("run_experiments")
        promotion = registry.get("draft_promotion")
        rebuttal = registry.get("draft_rebuttal")
        benchmark = registry.get("benchmark_evaluation")

        self.assertIsNotNone(search)
        self.assertEqual(search.agent_name, "retriever_agent")
        self.assertTrue(search.required)
        self.assertEqual(search.max_retries, 1)
        self.assertIsNotNone(search.handler)

        self.assertIsNotNone(rank)
        self.assertEqual(rank.agent_name, "paper_triage_agent")
        self.assertTrue(rank.required)
        self.assertIsNotNone(rank.handler)

        self.assertIsNotNone(reader)
        self.assertEqual(reader.agent_name, "paper_reader_agent")
        self.assertTrue(reader.required)
        self.assertIsNotNone(reader.handler)

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.agent_name, "evidence_agent")
        self.assertTrue(evidence.required)
        self.assertIsNotNone(evidence.handler)

        self.assertIsNotNone(synthesis)
        self.assertEqual(synthesis.agent_name, "synthesis_agent")
        self.assertTrue(synthesis.required)
        self.assertIsNotNone(synthesis.handler)

        self.assertIsNotNone(verifier)
        self.assertEqual(verifier.agent_name, "verifier_agent")
        self.assertTrue(verifier.required)
        self.assertIsNotNone(verifier.handler)

        self.assertIsNotNone(final_qa)
        self.assertEqual(final_qa.agent_name, "final_qa_agent")
        self.assertTrue(final_qa.required)
        self.assertIsNotNone(final_qa.handler)

        self.assertIsNotNone(compare)
        self.assertFalse(compare.required)
        self.assertIsNotNone(compare.handler)

        self.assertIsNotNone(ideas)
        self.assertFalse(ideas.required)
        self.assertIsNotNone(ideas.handler)

        self.assertIsNotNone(method)
        self.assertFalse(method.required)
        self.assertIsNotNone(method.handler)

        self.assertIsNotNone(evaluation)
        self.assertFalse(evaluation.required)
        self.assertIsNotNone(evaluation.handler)

        self.assertIsNotNone(run_experiments)
        self.assertEqual(run_experiments.agent_name, "experiment_agent")
        self.assertFalse(run_experiments.required)
        self.assertIsNotNone(run_experiments.handler)

        self.assertIsNotNone(promotion)
        self.assertFalse(promotion.required)
        self.assertIsNotNone(promotion.handler)

        self.assertIsNotNone(rebuttal)
        self.assertFalse(rebuttal.required)
        self.assertIsNotNone(rebuttal.handler)

        self.assertIsNotNone(benchmark)
        self.assertEqual(benchmark.agent_name, "benchmark_agent")
        self.assertFalse(benchmark.required)
        self.assertIsNotNone(benchmark.handler)

    def test_unknown_task_has_default_agent_name(self) -> None:
        self.assertEqual(AgentRegistry().agent_name_for("new_task"), "new_task_agent")


if __name__ == "__main__":
    unittest.main()
