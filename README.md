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
config/                     MCP server definitions
knowledge/                  Markdown knowledge base
servers/                   Built-in SQLite MCP server
benchmarks/                Tool retrieval evaluation set
scripts/                   Initialization and benchmark scripts
src/llm_mcp_rag/           Core application
  agent.py                 Agent loop and parallel tool execution
  query_understanding.py   Query routing
  knowledge_retriever.py   Knowledge chunk retrieval
  tool_retriever.py       Semantic MCP tool retrieval
  mcp_client.py            MCP v2 client wrapper
  mcp_registry.py          Multi-server tool registry
  vector_store.py          Small local vector index
  evaluation.py            Retrieval evaluation metrics
  runtime.py               Runtime trace
  bootstrap.py             Application assembly

tests/                     Unit and regression tests
```

## Setup

1. Create `.env` from `.env.example` and configure an OpenAI-compatible LLM / embedding endpoint.
2. Install the project in editable mode:

```bash
pip install -e .
```

3. Initialize the demo database:

```bash
python scripts/init_demo_db.py
```

4. Make sure `npx` and `uvx` are available for the optional File / Web MCP servers.
5. Start the Agent:

```bash
python -m llm_mcp_rag.main
```

## Evaluation

Run the unit tests:

```bash
pytest -q
```

Run semantic MCP Tool Retrieval evaluation:

```bash
python scripts/benchmark_tool_retrieval.py --ks 1 3 5
```

Stress-test a growing tool catalog:

```bash
python scripts/benchmark_tool_retrieval.py --ks 1 3 5 --scale 20 50 100
```

Results are written to `data/tool_retrieval_benchmark.json`.

### Experimental interpretation

The All-Tools baseline has full tool coverage by construction, but its tool-definition context grows with the total number of registered tools. The semantic router trades a small retrieval step for a smaller candidate set. The main experiment therefore compares Top-K retrieval quality against context-size reduction as the tool catalog grows.
