# MCP-RAG Agent V2

一个面向 MCP Tool Calling 的语义路由 Agent：同时检索知识与 MCP 工具，只把与当前 Query 相关的 Top-K 工具注入 LLM，再通过 MCP Client 完成多轮 Tool Calling。

## Architecture

```text
User Query
    |
    v
Query Understanding
    |
    +-----------------------+
    |                       |
    v                       v
Knowledge Retriever    Tool Retriever
    |                       |
    v                       v
Top-K Documents        Top-K MCP Tools
    |                       |
    +-----------+-----------+
                |
                v
           LLM Agent
                |
           Tool Calling
                |
                v
           MCP Registry
        +-------+-------+
        |       |       |
       File    Web      DB
        |       |       |
        +-------+-------+
                |
                v
           Tool Results
                |
                v
          LLM Reasoning
                |
                v
          Final Answer
```

## Engineering highlights

- **Semantic MCP Tool Retrieval**: 使用 MCP Tool name、description 和 input schema 建立向量索引，仅将与 Query 最相关的 Top-K 工具交给 LLM。
- **Dual Retrieval**: Query Understanding 同时生成 knowledge query / tool query，知识检索与工具检索可并发执行。
- **Tool Registry**: 使用 `server__tool` qualified name 解决多个 MCP Server 之间的同名工具冲突。
- **Async execution**: LLM、Embedding 和 MCP Tool Calling 均采用异步接口；同一轮返回的独立 Tool Calls 使用 `asyncio.gather()` 并发执行。
- **Safety boundary**: 内置只读 SQLite MCP Server；SQL 查询在 MCP Server 内再次校验，只允许只读语句。
- **Runtime trace**: 为 Query Understanding、Retrieval、LLM Round 和 Tool Execution 记录 trace、耗时及错误。
- **Cache**: Knowledge / Tool embedding index 根据内容 fingerprint 缓存，避免每次启动重复生成向量。
- **Evaluation**: 对 Tool Retriever 提供 Hit@K、Recall@K、MRR、平均候选数、上下文压缩率和检索延迟指标，并支持用 synthetic decoys 将 MCP catalog 扩展到 20 / 50 / 100 tools 进行压力实验。

## Project structure

```text
run.py                     Launcher: python run.py
config/                    MCP server definitions
servers/                   Built-in SQLite MCP server
benchmarks/                Tool retrieval evaluation set and recorded results
scripts/                   Initialization, diagnostic and benchmark scripts
src/                       Core application (Python package `src`)
  knowledge/               Markdown knowledge base
  agent.py                 Agent loop and parallel tool execution
  query_understanding.py   Query routing
  knowledge_retriever.py   Knowledge chunk retrieval
  tool_retriever.py       Semantic MCP tool retrieval
  mcp_client.py            MCP client wrapper
  mcp_registry.py          Multi-server tool registry
  vector_store.py          Small local vector index
  evaluation.py            Retrieval evaluation metrics
  runtime.py               Runtime trace
  bootstrap.py             Application assembly
```

## Setup

1. Create `.env` from `.env.example` and configure an OpenAI-compatible LLM / embedding endpoint.
2. Install the project and its dependencies:

```bash
pip install -e .
```

3. Initialize the demo database:

```bash
python scripts/init_demo_db.py
```

4. Make sure `npx` and `uvx` are available for the optional File / Web MCP servers.
   `config/mcp_servers.json` launches the File server through `cmd /c npx`, which is **Windows-only**; on macOS / Linux change it to `"command": "npx"` and drop the `"/c"` argument.
5. Start the Agent from the project root (any of the following):

```bash
python run.py
python -m src.main
```

Do not run `python src/main.py` directly: the modules use relative imports and must be run as part of the `src` package.

Relative paths written by the File MCP server (e.g. `report.md`) land in the project root.

Check that every MCP server can connect:

```bash
python scripts/diag_connect.py
```

## Evaluation

Run semantic MCP Tool Retrieval evaluation (20 hand-written queries in `benchmarks/tool_retrieval_cases.json`):

```bash
python scripts/benchmark_tool_retrieval.py --ks 1 3 5
```

Stress-test a growing tool catalog:

```bash
python scripts/benchmark_tool_retrieval.py --ks 1 3 5 --scale 20 50 100
```

Results are written to `data/tool_retrieval_benchmark.json`.

Expected tool names in the cases use the `server__tool` form (e.g. `file__read_file`), so the server names in `config/mcp_servers.json` must match. Cases whose expected tools are missing from the discovered catalog are **skipped**; the script prints a warning when that happens, and metrics should only be quoted when no case was skipped.

### Results

One complete run: 20 hand-written cases, a real 18-tool catalog and synthetic decoys up to 100 tools, Top-K retrieval over the raw query (all 20 cases evaluated in every catalog).

| Catalog size | Hit@1 | Hit@3 | Hit@5 | MRR | All-tools context (est. tokens) | Top-5 context (est. tokens) | Context reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 18 (real) | 85% | 95% | 100% | 0.9125 | 2475 | 685 | 72.3% |
| 20 | 85% | 95% | 100% | 0.9125 | 2562 | 682 | 73.4% |
| 50 | 80% | 90% | 100% | 0.8725 | 3862 | 599 | 84.5% |
| 100 | 80% | 90% | 95% | 0.8625 | 6034 | 596 | 90.1% |

At 100 tools, passing only the Top-5 tools cuts the estimated tool-definition context by about 90% while the expected tool was still among the Top-5 for 19 of 20 cases. Token counts are heuristic estimates, and the reduction rises with catalog size by construction (Top-5 always passes 5 tools), so it should be read together with Hit@5 rather than on its own.

The failures are analysed in [`benchmarks/results/tool_retrieval_20cases.md`](benchmarks/results/tool_retrieval_20cases.md): three of them involve functionally overlapping file tools (`read_file` / `read_text_file`), and the single Hit@5 miss at 100 tools is caused by about ten near-identical synthetic `analytics` decoys filling the Top-5.

## Known limitations

- **Small-scale vector index**: `vector_store.py` is an in-memory brute-force cosine search built on NumPy. It is fine for a demo-sized knowledge base and tool catalog, but is not an ANN index or a persistent vector database.
- **Dense-only knowledge retrieval**: document retrieval uses embedding similarity only, with no BM25 hybrid search, reranking or chunking-strategy comparison.
- **Small evaluation set**: the tool retrieval benchmark has 20 hand-written queries with no held-out test split, so one case is 5 percentage points and the confidence intervals are wide (85% is roughly 64% to 95%). The numbers indicate a trend, not production performance.
- **Synthetic decoys**: larger catalogs are padded with unrelated tools generated from eight repeated templates, so about ten decoys can be near-identical. This inflates crowding effects and is unlike a real catalog.
- **Raw-query evaluation**: the benchmark retrieves with the raw query, while the application uses the LLM-rewritten `tool_query`; the exact production path is not measured yet.
- **Label ambiguity**: functionally overlapping tools such as `read_file` and `read_text_file` are scored as strictly different, which lowers Hit@1.
- **Retrieval-level evaluation only**: tool retrieval and tool selection are measured, but final answer quality (faithfulness, correctness) is not evaluated yet.
- **External model dependency**: results depend on the configured LLM / embedding endpoints (default: DeepSeek chat + DashScope embeddings).
- **Windows-oriented MCP config**: see Setup step 4.

## Roadmap

- Add unit tests for `vector_store`, `evaluation` metrics and config parsing.
- Split the benchmark into a tuning set and a held-out test set, and report strict and equivalence-aware scores.
- Replace the repeated-template decoys with distinct ones, and add a `--rewrite` mode that evaluates the Query Understanding output.
- Record the embedding model, parameters, date and code version in every benchmark report.
- Add hybrid retrieval (BM25 + vector) and a reranker, compared on a larger labelled query set.
- Add answer-quality evaluation and an HTTP API with streaming responses.
