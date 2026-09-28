# Tool Retrieval Benchmark

This benchmark answers a concrete engineering question:

> When the MCP catalog grows, can semantic tool retrieval keep the model's tool context small while retaining the relevant tool?

## Metrics

- **Hit@K**: at least one expected tool appears in the top K.
- **Recall@K**: fraction of expected tools recovered in the top K.
- **MRR**: reciprocal rank of the first relevant tool.
- **Context reduction**: estimated reduction in serialized tool-definition tokens versus passing all tools.
- **Retrieval latency**: embedding + vector search time for one query.

The all-tools baseline has full tool coverage by construction, so it is not assigned a ranking score. It is used as the context-size baseline.

## Run

After installing the project dependencies and configuring `.env`:

```bash
python scripts/benchmark_tool_retrieval.py --ks 1 3 5 --scale 20 50 100
```

The script discovers real MCP tools from `config/mcp_servers.json`. `--scale` adds synthetic unrelated tools so the retrieval strategy can be stress-tested as the catalog grows. Results are written to `data/tool_retrieval_benchmark.json`.
