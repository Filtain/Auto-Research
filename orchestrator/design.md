# Orchestrator 主控层设计

日期：2026-05-13

## 1. 定位

Orchestrator 是整个 Auto Research 系统的最高控制层，相当于“科研项目经理”或“总调度中心”。

它不负责亲自完成所有科研任务，而是负责判断用户意图、制定研究路线、拆解任务、调度不同 Agent、追踪执行状态，并在必要时触发验证、重试、返工和结果合并。

在整个系统中，Orchestrator 是连接用户输入、Agent 执行、知识库、验证系统和最终导出模块的核心枢纽。

## 2. 核心作用

Orchestrator 需要先理解用户真正想完成的科研任务。例如用户输入：

```text
我想研究 NeRF 中多分辨率表示方法的发展，并找出 BANF 的创新点。
```

Orchestrator 不能直接开始写报告，而应该先判断这个任务包含多个阶段：

```text
1. 文献检索
2. 论文筛选
3. 方法阅读
4. 技术路线梳理
5. 创新点分析
6. 对比总结
7. 最终报告生成
```

然后它创建任务图，把任务分发给不同模块。

## 3. 主要职责

### 3.1 用户目标解析

Orchestrator 首先要把用户的自然语言请求转成结构化任务描述。

用户输入：

```text
帮我调研 3D Gaussian Splatting 和 NeRF 的区别，并生成一个 PPT 大纲。
```

解析后得到：

```json
{
  "research_topic": "3D Gaussian Splatting vs NeRF",
  "task_type": ["literature_review", "method_comparison", "ppt_generation"],
  "domain": "computer_vision",
  "output_format": "ppt_outline",
  "depth": "medium",
  "need_citations": true,
  "need_figures": true
}
```

这一层的关键是识别用户到底要什么，而不是只看表面关键词。

### 3.2 任务阶段判断

Orchestrator 需要判断当前任务属于科研流程中的哪几个阶段。

科研任务阶段：

```text
Literature Review：文献综述
Idea Generation：研究 idea 生成
Method Design：方法设计
Experiment Planning：实验方案设计
Paper Writing：论文写作
Evaluation：结果评估
Rebuttal：审稿回复
Promotion：论文展示、PPT、海报、博客
```

示例：

| 用户需求 | 阶段判断 |
| --- | --- |
| 帮我找 BANF 相关论文 | Literature Review |
| 帮我分析这篇论文创新点 | Literature Review + Method Analysis |
| 帮我设计一个改进 BANF 的 idea | Idea Generation + Method Design |
| 帮我规划复现实验 | Experiment Planning |
| 帮我写论文 introduction | Paper Writing |
| 帮我准备答辩 PPT | Promotion |

这个判断结果会影响后续调用哪些 Agent。

### 3.3 任务拆解

Orchestrator 会把大任务拆成多个可执行子任务。

例如用户输入：

```text
帮我做一个关于 BANF 的完整论文调研，并给出复现建议。
```

拆解结果：

```json
{
  "tasks": [
    {
      "id": "T1",
      "name": "generate_search_queries",
      "agent": "query_agent",
      "depends_on": []
    },
    {
      "id": "T2",
      "name": "search_papers",
      "agent": "retriever_agent",
      "depends_on": ["T1"]
    },
    {
      "id": "T3",
      "name": "rank_papers",
      "agent": "ranking_agent",
      "depends_on": ["T2"]
    },
    {
      "id": "T4",
      "name": "read_core_papers",
      "agent": "paper_reader_agent",
      "depends_on": ["T3"]
    },
    {
      "id": "T5",
      "name": "extract_method_details",
      "agent": "method_extractor_agent",
      "depends_on": ["T4"]
    },
    {
      "id": "T6",
      "name": "compare_methods",
      "agent": "comparison_agent",
      "depends_on": ["T5"]
    },
    {
      "id": "T7",
      "name": "generate_reproduction_plan",
      "agent": "experiment_agent",
      "depends_on": ["T5", "T6"]
    },
    {
      "id": "T8",
      "name": "verify_claims",
      "agent": "verifier_agent",
      "depends_on": ["T6", "T7"]
    },
    {
      "id": "T9",
      "name": "generate_final_report",
      "agent": "writer_agent",
      "depends_on": ["T8"]
    }
  ]
}
```

这样系统就不是“一个大模型直接从头写到尾”，而是变成有流程、有依赖、有检查的科研流水线。

## 4. Orchestrator 不应该做什么

Orchestrator 本身不应该直接承担专业科研判断，否则容易出现幻觉和越权。

它不应该：

```text
1. 不直接编造论文结论。
2. 不直接判断某篇论文是否 SOTA，除非有证据。
3. 不跳过 citation 验证。
4. 不在没有阅读原文的情况下写最终报告。
5. 不把用户模糊需求直接变成确定结论。
6. 不把不同来源的内容混在一起却不保留出处。
7. 不直接修改实验结果。
```

更准确地说，Orchestrator 可以做“管理判断”，但不能做“无证据科研判断”。

它可以判断：

```text
当前信息不足，需要继续检索。
当前引用缺失，需要进入 verifier。
当前报告没有达到输出要求，需要返工。
```

它不应该直接说：

```text
BANF 一定优于所有 NeRF 方法。
这篇论文肯定是最先进方法。
这个实验一定能成功。
```

## 5. 输入

Orchestrator 的输入主要包括三类。

### 5.1 用户输入

```json
{
  "user_query": "帮我调研 BANF 的方法结构，并生成 PPT 大纲",
  "output_format": "ppt",
  "language": "zh",
  "depth": "detailed"
}
```

### 5.2 系统上下文

```json
{
  "available_tools": [
    "web_search",
    "paper_parser",
    "vector_db",
    "citation_verifier",
    "report_writer",
    "ppt_generator"
  ],
  "available_agents": [
    "retriever_agent",
    "paper_reader_agent",
    "method_extractor_agent",
    "comparison_agent",
    "experiment_agent",
    "writer_agent",
    "verifier_agent"
  ]
}
```

### 5.3 历史上下文

```json
{
  "previous_research_topic": "BANF",
  "known_user_preference": {
    "focus": ["network_structure", "input_output", "reproduction"],
    "style": "detailed and practical"
  }
}
```

## 6. 输出

Orchestrator 的输出不是最终论文内容，而是整个研究流程的控制文件。

核心产物：

```text
research_plan.json
task_graph.json
run_log.json
artifact_manifest.json
final_decision.json
```

## 7. 控制文件

### 7.1 research_plan.json

`research_plan.json` 用来描述本次研究任务的整体计划。

```json
{
  "project_id": "auto_research_20260513_001",
  "topic": "BANF: Band-limited Neural Fields for Levels of Detail Reconstruction",
  "goal": "Analyze the method architecture, input-output flow, innovation, and reproduction plan.",
  "task_type": [
    "literature_review",
    "method_analysis",
    "experiment_planning",
    "ppt_generation"
  ],
  "research_questions": [
    "What problem does BANF solve?",
    "How does BANF implement band-limited neural fields?",
    "What are the inputs and outputs of each module?",
    "How is BANF different from NeRF and Instant-NGP?",
    "How can the method be reproduced?"
  ],
  "expected_artifacts": [
    "paper_summary.md",
    "method_structure.md",
    "comparison_table.csv",
    "reproduction_plan.md",
    "ppt_outline.md"
  ],
  "quality_requirements": {
    "need_citations": true,
    "need_source_trace": true,
    "need_verification": true,
    "allow_uncertain_claims": false
  }
}
```

### 7.2 task_graph.json

`task_graph.json` 是 Orchestrator 最核心的调度文件，用来描述任务依赖关系。

```json
{
  "nodes": [
    {
      "task_id": "T1",
      "task_name": "search_related_papers",
      "agent": "retriever_agent",
      "status": "pending",
      "input": {
        "query": "BANF band-limited neural fields NeRF LOD"
      },
      "output": null,
      "depends_on": []
    },
    {
      "task_id": "T2",
      "task_name": "parse_core_paper",
      "agent": "paper_reader_agent",
      "status": "pending",
      "input": {
        "paper_id": "BANF_2024"
      },
      "output": null,
      "depends_on": ["T1"]
    },
    {
      "task_id": "T3",
      "task_name": "extract_network_structure",
      "agent": "method_extractor_agent",
      "status": "pending",
      "input": {
        "focus": ["module", "input", "output", "loss", "training"]
      },
      "output": null,
      "depends_on": ["T2"]
    }
  ]
}
```

这个结构可以直接映射成 DAG，也就是有向无环任务图。

### 7.3 run_log.json

`run_log.json` 记录整个运行过程，方便 Debug 和复盘。

```json
{
  "project_id": "auto_research_20260513_001",
  "logs": [
    {
      "time": "2026-05-13T20:30:00",
      "task_id": "T1",
      "agent": "retriever_agent",
      "status": "started"
    },
    {
      "time": "2026-05-13T20:30:15",
      "task_id": "T1",
      "agent": "retriever_agent",
      "status": "completed",
      "summary": "Found 12 related papers."
    },
    {
      "time": "2026-05-13T20:31:10",
      "task_id": "T2",
      "agent": "paper_reader_agent",
      "status": "failed",
      "error": "PDF parsing failed on page 6."
    },
    {
      "time": "2026-05-13T20:31:15",
      "task_id": "T2_retry_1",
      "agent": "paper_reader_agent",
      "status": "started",
      "reason": "Retry with OCR parser."
    }
  ]
}
```

这个文件很重要，因为 Auto Research 系统任务链较长，没有日志就很难定位哪里出错。

### 7.4 artifact_manifest.json

`artifact_manifest.json` 记录最终生成了哪些文件，以及这些文件来自哪些任务。

```json
{
  "project_id": "auto_research_20260513_001",
  "artifacts": [
    {
      "name": "paper_summary.md",
      "type": "markdown",
      "created_by": "writer_agent",
      "source_tasks": ["T2", "T3", "T4"],
      "verified": true
    },
    {
      "name": "comparison_table.csv",
      "type": "csv",
      "created_by": "comparison_agent",
      "source_tasks": ["T3", "T4"],
      "verified": true
    },
    {
      "name": "ppt_outline.md",
      "type": "markdown",
      "created_by": "ppt_agent",
      "source_tasks": ["T5", "T6"],
      "verified": false
    }
  ]
}
```

它的作用是保证最终产物可追踪。

## 8. 状态机

Orchestrator 可以设计成状态机。

```text
INIT
  ↓
UNDERSTAND_QUERY
  ↓
PLAN_TASKS
  ↓
BUILD_TASK_GRAPH
  ↓
DISPATCH_AGENTS
  ↓
MONITOR_PROGRESS
  ↓
COLLECT_RESULTS
  ↓
VERIFY_RESULTS
  ↓
NEED_REWORK? -- yes -> REPLAN / REDISPATCH
  ↓ no
GENERATE_ARTIFACTS
  ↓
FINAL_CHECK
  ↓
EXPORT
  ↓
DONE
```

| 状态 | 含义 |
| --- | --- |
| INIT | 初始化项目 |
| UNDERSTAND_QUERY | 理解用户需求 |
| PLAN_TASKS | 制定研究计划 |
| BUILD_TASK_GRAPH | 构建任务图 |
| DISPATCH_AGENTS | 分发任务 |
| MONITOR_PROGRESS | 监控执行状态 |
| COLLECT_RESULTS | 收集各 Agent 输出 |
| VERIFY_RESULTS | 验证引用和结论 |
| REPLAN | 如果失败或信息不足，重新规划 |
| GENERATE_ARTIFACTS | 生成报告、表格、PPT 等 |
| FINAL_CHECK | 最终质量检查 |
| EXPORT | 导出文件 |
| DONE | 完成 |

## 9. Agent 调度策略

### 9.1 串行调度

适合强依赖任务。

```text
检索论文 -> 阅读论文 -> 提取方法 -> 生成报告
```

优点是稳定，缺点是慢。

### 9.2 并行调度

适合多个 Agent 同时处理不同论文。

```text
Paper Reader Agent 1 -> 读论文 A
Paper Reader Agent 2 -> 读论文 B
Paper Reader Agent 3 -> 读论文 C
```

适合大量论文综述。

### 9.3 混合调度

最推荐。

```text
先串行完成检索和筛选
然后并行阅读多篇论文
最后串行合并、验证和写作
```

例如：

```text
Query Generation
      ↓
Paper Search
      ↓
Paper Ranking
      ↓
[Paper Reader 1] [Paper Reader 2] [Paper Reader 3]
      ↓
Method Comparison
      ↓
Verifier
      ↓
Writer
```

这个模式最适合 Auto Research。

## 10. 返工机制

Orchestrator 必须支持返工，否则生成结果很容易不可靠。

常见返工条件：

```text
1. 检索到的论文数量不足。
2. 核心论文缺少 PDF。
3. 某篇论文解析失败。
4. 某个结论没有引用来源。
5. 不同 Agent 的结论冲突。
6. 用户要求的输出格式不完整。
7. verifier 判断存在 hallucination 风险。
```

返工策略：

```json
{
  "rework_rules": [
    {
      "condition": "paper_count < min_required",
      "action": "expand_search_queries"
    },
    {
      "condition": "claim_without_citation == true",
      "action": "send_to_verifier"
    },
    {
      "condition": "method_description_conflict == true",
      "action": "reread_source_sections"
    },
    {
      "condition": "output_format_incomplete == true",
      "action": "send_back_to_writer"
    }
  ]
}
```

## 11. 质量控制标准

Orchestrator 在决定是否进入最终导出前，需要检查几个指标。

```json
{
  "quality_check": {
    "has_clear_research_question": true,
    "has_sufficient_sources": true,
    "has_citations_for_key_claims": true,
    "has_method_comparison": true,
    "has_limitations": true,
    "has_uncertainty_marked": true,
    "has_final_output": true
  }
}
```

如果某项不通过，就不能直接导出。

例如：

```text
如果核心结论没有 citation -> 返回 verifier。
如果方法对比表缺少某篇论文 -> 返回 comparison_agent。
如果实验方案不具体 -> 返回 experiment_agent。
如果最终报告结构混乱 -> 返回 writer_agent。
```

## 12. 伪代码

```python
class ResearchOrchestrator:
    def __init__(self, agents, tools, memory, artifact_store):
        self.agents = agents
        self.tools = tools
        self.memory = memory
        self.artifact_store = artifact_store

    def run(self, user_query):
        intent = self.understand_query(user_query)
        research_plan = self.create_research_plan(intent)
        task_graph = self.build_task_graph(research_plan)

        while not task_graph.is_finished():
            ready_tasks = task_graph.get_ready_tasks()

            for task in ready_tasks:
                agent = self.select_agent(task)
                result = agent.run(task.input)

                if result.status == "success":
                    task_graph.update_task(task.id, result)
                else:
                    self.handle_failure(task, result, task_graph)

            if self.need_verification(task_graph):
                verification_result = self.verify(task_graph)

                if not verification_result.passed:
                    self.replan(task_graph, verification_result)

        artifacts = self.generate_artifacts(task_graph)

        final_check = self.final_check(artifacts)

        if final_check.passed:
            return self.export(artifacts)
        return self.rework(artifacts, final_check)
```

## 13. 推荐技术实现

### 后端语言

```text
Python
```

原因：科研工具链、PDF 解析、向量数据库、LLM Agent 框架都更成熟。

### Agent 框架

可选：

```text
LangGraph：适合做任务图、状态机、多 Agent 流程。
LlamaIndex Workflow：适合 RAG 和文档研究。
CrewAI：适合快速搭多 Agent demo。
AutoGen：适合多 Agent 对话协作。
```

严谨项目优先：

```text
LangGraph + FastAPI + PostgreSQL + FAISS/Chroma
```

### 状态存储

```text
短期状态：Redis
长期状态：PostgreSQL
文档向量：FAISS / Chroma / Milvus
文件存储：本地磁盘 / MinIO / S3
日志追踪：JSONL + 数据库
```

## 14. 文件位置

本模块后续文件建议放在：

```text
orchestrator/
  README.md
  design.md
  prompts/
  schemas/
  sql/
  examples/
  src/
  tests/
```
