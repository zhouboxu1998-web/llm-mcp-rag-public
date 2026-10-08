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

## Checking that a run is valid

Before quoting any number, confirm that every case was evaluated:

```bash
python -c "import json; b=json.load(open('data/tool_retrieval_benchmark.json',encoding='utf-8')); [print('N=',c['tool_count'],'evaluated',sum(1 for x in c['cases'] if not x.get('skipped')),'/',len(c['cases']),'Hit',c['semantic_top_k']['hit_at_k'],'MRR',c['semantic_top_k']['mrr']) for c in b['catalog_benchmarks']]"
```

Every line must read `evaluated 20 / 20`. Expected tool names use the `server__tool` form, so server names in `config/mcp_servers.json` must match the cases; the script prints a `[WARNING]` when cases are skipped.

## Results

A recorded run (20/20 cases, 18 to 100 tools) with error analysis and known gaps is in [`results/tool_retrieval_20cases.md`](results/tool_retrieval_20cases.md). Summary:

| Catalog size | Hit@1 | Hit@3 | Hit@5 | MRR | All-tools context (est. tokens) | Top-5 context (est. tokens) | Context reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 18 (real) | 85% | 95% | 100% | 0.9125 | 2475 | 685 | 72.3% |
| 20 | 85% | 95% | 100% | 0.9125 | 2562 | 682 | 73.4% |
| 50 | 80% | 90% | 100% | 0.8725 | 3862 | 599 | 84.5% |
| 100 | 80% | 90% | 95% | 0.8625 | 6034 | 596 | 90.1% |
