# Tool retrieval benchmark: 20 cases, 18 to 100 tools

A record of one complete, valid run of `scripts/benchmark_tool_retrieval.py --ks 1 3 5 --scale 20 50 100`.

## Setup

- Cases: 20 hand-written queries in `benchmarks/tool_retrieval_cases.json`; every case was evaluated in every catalog (20/20, none skipped).
- Real catalog: 18 tools from three MCP servers (`file` 14 tools, `fetch` 1 tool, `sqlite` 3 tools).
- Larger catalogs (20 / 50 / 100): the real tools plus synthetic decoy tools from `add_synthetic_tool_decoys`.
- Retrieval: embedding similarity over each tool's server, name, description and input schema; the query is the **raw case query**; `--min-score` was left at the default `-1.0` (no score threshold); K = 1, 3, 5.
- Embedding and LLM endpoints are configured in `.env` (defaults in `.env.example`). The report JSON did not record the embedding model, run date or code version at the time of this run.

## Results

| Catalog size | Hit@1 | Hit@3 | Hit@5 | MRR | All-tools context (est. tokens) | Top-5 context (est. tokens) | Context reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 18 (real) | 85% | 95% | 100% | 0.9125 | 2475 | 685 | 72.3% |
| 20 | 85% | 95% | 100% | 0.9125 | 2562 | 682 | 73.4% |
| 50 | 80% | 90% | 100% | 0.8725 | 3862 | 599 | 84.5% |
| 100 | 80% | 90% | 95% | 0.8625 | 6034 | 596 | 90.1% |

Recall@K equals Hit@K at K = 3 and 5. At K = 1 it is 80% (N = 18, 20) and 75% (N = 50, 100), because some cases expect two tools and a single slot cannot cover both. Average retrieval latency was 232 to 250 ms per query, dominated by the embedding API call. It comes from a single run, so differences of a few milliseconds between catalog sizes are noise.

## How to read these numbers

- With 20 cases, one case is 5 percentage points. The 95% Wilson interval for 17/20 is roughly 64% to 95%, so 85% versus 80% is a one-case difference, not evidence of a trend.
- Context reduction is mostly arithmetic: Top-5 always passes 5 tools, so the reduction grows with catalog size regardless of retrieval quality. The meaningful statement is the trade-off: about 90% less tool context at 100 tools while the expected tool was still in the Top-5 for 19 of 20 cases.
- Hit@5 and Recall@5 matter more for this system than Hit@1, because the LLM receives all Top-5 tools and chooses among them.

## Error analysis

Failures at N = 18 (not ranked first):

| Query | Expected | Top-3 | Interpretation |
|---|---|---|---|
| 读取项目目录下的文件内容 | `file__read_file` | `list_directory`, `read_text_file`, `read_multiple_files` | Ambiguous query; the word "directory" pulls retrieval toward `list_directory`. A genuine confusion. |
| 查看 README.md 文件的内容 | `file__read_file` | `read_text_file`, `read_file`, `read_media_file` | `read_text_file` overlaps with `read_file`; mostly a labelling issue. |
| 读取配置文件并保存一份副本 | `file__read_file`, `file__write_file` | `read_text_file`, `read_file`, `write_file` | Both expected tools are in the Top-3; Hit@1 is a strict-metric false negative. |

Failure at N = 100 (expected tool missing from the Top-5):

| Query | Expected | Top-5 |
|---|---|---|
| 把分析结果写入 report.md | `file__write_file` | five `synthetic_analytics__action_*` tools |

The synthetic generator repeats one template per category, so at N = 100 there are about ten near-identical `analytics` decoys ("Run predefined business analytics and KPI reports"). The query's "分析" and "report" match them, and five near-duplicates fill every Top-5 slot. This case ranked first at N = 18 and was still a hit at N = 50. It is largely an artifact of the decoy construction, but it also shows that Top-K has no diversity control and that topical words can outweigh the action intent.

## Validity history

An earlier run reported Hit@5 = 100% and MRR = 1.0 on every catalog size. In that run the file server had been renamed from `file` to `filesystem` while the cases still expected `file__*` tool names, so 10 of 20 cases were silently skipped and only the easiest 10 were scored. The server name was restored, the script now prints a warning whenever cases are skipped, and the numbers above come from a run with 20/20 cases evaluated.

## Known gaps of this benchmark

- The benchmark embeds the raw query, while the application retrieves tools with `plan.tool_query`, the LLM-rewritten query from Query Understanding. The benchmark therefore does not measure the exact production path.
- Labels follow the tool names in the case file; functionally overlapping tools (`read_file`, `read_text_file`) are scored as strictly different.
- The cases were written and inspected by the same person, with no held-out test split.
- Real tools embed a long input schema while decoys embed an empty one; whether this length difference favours decoys has not been tested.
