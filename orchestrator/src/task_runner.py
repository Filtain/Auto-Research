from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from orchestrator.src.agent_registry import AgentRegistry


TERMINAL_STATUSES = {"completed", "failed", "blocked", "skipped"}


@dataclass
class TaskRunResult:
    status: str
    output: dict[str, Any]
    summary: str = ""
    error: str = ""


TaskHandler = Callable[[Any, Path], TaskRunResult]
LogCallback = Callable[[Any, str, str, str], None]


class TaskRunner:
    """Execute a task graph as a DAG using registered task handlers.

    The runner is deliberately strict: tasks without handlers are blocked,
    and downstream tasks are blocked if dependencies fail or block. This keeps
    the orchestrator from pretending unfinished research work is complete.
    """

    def __init__(
        self,
        output_dir: Path | str,
        registry: AgentRegistry | None = None,
        handlers: dict[str, TaskHandler] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.registry = registry or AgentRegistry()
        self.handlers: dict[str, TaskHandler] = {}
        if handlers:
            self.handlers.update(handlers)

    def run(self, task_graph: Any, log: LogCallback | None = None) -> None:
        nodes_by_id = {node.task_id: node for node in task_graph.nodes}

        while True:
            pending_nodes = [node for node in task_graph.nodes if node.status == "pending"]
            if not pending_nodes:
                return

            progressed = False
            for node in pending_nodes:
                dependency_statuses = [
                    nodes_by_id[dependency_id].status
                    for dependency_id in node.depends_on
                    if dependency_id in nodes_by_id
                ]

                missing_dependencies = [
                    dependency_id for dependency_id in node.depends_on if dependency_id not in nodes_by_id
                ]
                if missing_dependencies:
                    self.block_node(
                        node,
                        reason=f"Missing dependencies: {', '.join(missing_dependencies)}",
                        log=log,
                    )
                    progressed = True
                    continue

                if any(status in {"failed", "blocked"} for status in dependency_statuses):
                    self.block_node(node, reason="A dependency failed or was blocked.", log=log)
                    progressed = True
                    continue

                if not all(status in {"completed", "skipped"} for status in dependency_statuses):
                    continue

                self.run_node(node, log=log)
                progressed = True

            if not progressed:
                for node in pending_nodes:
                    self.block_node(node, reason="No runnable dependency path remains.", log=log)
                return

    def run_node(self, node: Any, log: LogCallback | None = None) -> None:
        spec = self.registry.get(node.task_name)
        handler = self.handlers.get(node.task_name) or (spec.handler if spec else None)
        if handler is None:
            reason = f"No handler registered for task '{node.task_name}'."
            if spec and not spec.required:
                self.skip_node(node, reason=reason, log=log)
            else:
                self.block_node(node, reason=reason, log=log)
            return

        max_retries = spec.max_retries if spec else 0
        last_error = ""
        for attempt in range(max_retries + 1):
            node.status = "running"
            node.retry_count = attempt
            if log:
                log(node, "started", f"Running {node.task_name} (attempt {attempt + 1}).", "")
            try:
                raw_result = handler(node, self.output_dir)
                result = self.normalize_result(node=node, raw_result=raw_result)
            except Exception as exc:  # noqa: BLE001 - preserve failure in task graph.
                last_error = str(exc)
                if log:
                    log(node, "retrying" if attempt < max_retries else "failed", "", last_error)
                if attempt < max_retries:
                    continue
                node.status = "failed"
                node.output = {"error": last_error}
                return

            node.status = result.status
            node.output = result.output
            if log:
                log(node, result.status, result.summary, result.error)
            return

        node.status = "failed"
        node.output = {"error": last_error or "Unknown task failure."}

    def normalize_result(self, node: Any, raw_result: Any) -> TaskRunResult:
        if isinstance(raw_result, TaskRunResult):
            return raw_result
        if not isinstance(raw_result, dict):
            return TaskRunResult(
                status="failed",
                output={"error": "Handler returned an unsupported result type."},
                error="Handler returned an unsupported result type.",
            )

        if node.task_name == "search_sources" and int(raw_result.get("paper_count", 0)) <= 0:
            return TaskRunResult(
                status="blocked",
                output=raw_result,
                summary=f"Retrieved 0 papers with {raw_result.get('error_count', 0)} source errors.",
            )
        if node.task_name == "rank_sources" and int(raw_result.get("paper_count", 0)) <= 0:
            return TaskRunResult(
                status="blocked",
                output=raw_result,
                summary="Ranked 0 papers; paper triage cannot continue.",
            )

        summary = raw_result.get("summary")
        if not isinstance(summary, str) or not summary:
            summary = f"Completed {node.task_name}."
        return TaskRunResult(status="completed", output=raw_result, summary=summary)

    def block_node(self, node: Any, reason: str, log: LogCallback | None = None) -> None:
        node.status = "blocked"
        node.output = {"reason": reason}
        if log:
            log(node, "blocked", reason, "")

    def skip_node(self, node: Any, reason: str, log: LogCallback | None = None) -> None:
        node.status = "skipped"
        node.output = {"reason": reason}
        if log:
            log(node, "skipped", reason, "")
