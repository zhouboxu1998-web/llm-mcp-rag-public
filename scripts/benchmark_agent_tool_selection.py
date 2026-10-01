from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from src.config import Settings, load_mcp_server_configs
from src.evaluation import add_synthetic_tool_decoys, estimate_tool_context_tokens
from src.llm import LLMClient, tool_definition
from src.models import ToolBinding
from src.tool_retriever import ToolRetriever

DEFAULT_CASES = PROJECT_ROOT / "benchmarks" / "tool_retrieval_cases.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A/B benchmark for LLM MCP tool selection: all tools vs semantic Top-K.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "agent_tool_selection_benchmark.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--scale", nargs="*", type=int, default=[])
    return parser.parse_args()


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


async def discover_tools(settings: Settings) -> tuple[object, list[ToolBinding]]:
    from src.mcp_client import MCPClient
    from src.mcp_registry import MCPRegistry

    configs = load_mcp_server_configs(settings)
    clients = [
        MCPClient(
            name=item["name"],
            command=item["command"],
            args=item.get("args", []),
            env=item.get("env"),
            required=item.get("required", True),
        )
        for item in configs
    ]
    registry = MCPRegistry(clients)
    return registry, await registry.connect_all()


async def select_tools(llm: LLMClient, query: str, candidates: list[ToolBinding]) -> list[str]:
    system = (
        "You are an MCP tool selector. Decide which available tools are necessary for the user's task. "
        "Call every tool that is directly required and call no unnecessary tools. "
        "Do not execute tools in this benchmark; tool calls are recorded only for evaluation."
    )
    response = await llm.complete(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": query},
        ],
        tools=[tool_definition(tool) for tool in candidates],
    )
    return [call.name for call in response.tool_calls]


def score_selection(selected: list[str], expected: list[str]) -> dict[str, float | bool]:
    selected_set = set(selected)
    expected_set = set(expected)
    matched = len(selected_set & expected_set)
    precision = matched / max(1, len(selected_set))
    recall = matched / max(1, len(expected_set))
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "hit": matched > 0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


async def evaluate_catalog(
    *,
    settings: Settings,
    embedding,
    llm: LLMClient,
    bindings: list[ToolBinding],
    cases: list[dict],
    top_k: int,
) -> dict:
    retriever = ToolRetriever(embedding, settings.data_dir)
    await retriever.build(bindings)
    all_context_tokens = estimate_tool_context_tokens(bindings)
    baseline_scores = []
    topk_scores = []
    records = []

    for case in cases:
        expected = [name for name in case["expected_tools"] if name in {b.qualified_name for b in bindings}]
        if not expected:
            continue

        started = time.perf_counter()
        top_tools = await retriever.retrieve(case["query"], k=top_k, min_score=-1.0)
        retrieval_ms = (time.perf_counter() - started) * 1000
        top_names = [tool.qualified_name for tool in top_tools]

        all_selected = await select_tools(llm, case["query"], bindings)
        top_selected = await select_tools(llm, case["query"], top_tools)
        all_score = score_selection(all_selected, expected)
        top_score = score_selection(top_selected, expected)
        top_context_tokens = estimate_tool_context_tokens(top_tools)

        baseline_scores.append(all_score)
        topk_scores.append(top_score)
        records.append({
            "query": case["query"],
            "expected_tools": expected,
            "candidate_tools_top_k": top_names,
            "all_tools_selected": all_selected,
            "top_k_selected": top_selected,
            "all_tools": all_score,
            "top_k": top_score,
            "top_k_context_tokens_est": top_context_tokens,
            "context_reduction_pct": max(0.0, 1.0 - top_context_tokens / all_context_tokens) * 100 if all_context_tokens else 0.0,
            "retrieval_latency_ms": retrieval_ms,
        })

    def mean(name: str, group: list[dict]) -> float:
        return sum(float(item[name]) for item in group) / max(1, len(group))

    return {
        "tool_count": len(bindings),
        "cases": len(records),
        "all_tools": {
            "hit_rate": sum(bool(x["hit"]) for x in baseline_scores) / max(1, len(baseline_scores)),
            "precision": mean("precision", baseline_scores),
            "recall": mean("recall", baseline_scores),
            "f1": mean("f1", baseline_scores),
            "context_tokens_est": all_context_tokens,
        },
        "top_k": {
            "k": top_k,
            "hit_rate": sum(bool(x["hit"]) for x in topk_scores) / max(1, len(topk_scores)),
            "precision": mean("precision", topk_scores),
            "recall": mean("recall", topk_scores),
            "f1": mean("f1", topk_scores),
            "avg_context_tokens_est": sum(r["top_k_context_tokens_est"] for r in records) / max(1, len(records)),
            "avg_context_reduction_pct": sum(r["context_reduction_pct"] for r in records) / max(1, len(records)),
            "avg_retrieval_latency_ms": sum(r["retrieval_latency_ms"] for r in records) / max(1, len(records)),
        },
        "cases_detail": records,
    }


async def main() -> None:
    args = parse_args()
    if args.top_k <= 0:
        raise ValueError("--top-k must be positive")
    load_dotenv()
    settings = Settings.from_env()
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    from src.embeddings import EmbeddingClient

    embedding = EmbeddingClient(settings.embedding_api_key, settings.embedding_base_url, settings.embedding_model)
    registry, base_bindings = await discover_tools(settings)
    try:
        cases = load_cases(args.cases)
        sizes = [len(base_bindings)] + [size for size in sorted(set(args.scale)) if size > len(base_bindings)]
        reports = []
        for size in sizes:
            bindings = add_synthetic_tool_decoys(base_bindings, size)
            reports.append(await evaluate_catalog(
                settings=settings,
                embedding=embedding,
                llm=llm,
                bindings=bindings,
                cases=cases,
                top_k=args.top_k,
            ))

        payload = {
            "methodology": {
                "all_tools": "LLM receives the full discovered tool catalog",
                "top_k": f"LLM receives the semantic Top-{args.top_k} retrieved tools",
                "selection": "actual OpenAI-compatible tool calling; selected names are scored without executing them",
            },
            "catalog_benchmarks": reports,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=== Agent Tool Selection A/B Benchmark ===")
        for report in reports:
            print(f"\nCatalog tools={report['tool_count']}")
            print(f"All-tools: hit={report['all_tools']['hit_rate']:.2%} precision={report['all_tools']['precision']:.2%} recall={report['all_tools']['recall']:.2%} f1={report['all_tools']['f1']:.2%}")
            print(f"Top-{args.top_k}: hit={report['top_k']['hit_rate']:.2%} precision={report['top_k']['precision']:.2%} recall={report['top_k']['recall']:.2%} f1={report['top_k']['f1']:.2%}")
            print(f"Top-{args.top_k} context reduction={report['top_k']['avg_context_reduction_pct']:.2f}%")
            print(f"retrieval latency={report['top_k']['avg_retrieval_latency_ms']:.2f} ms")
        print(f"report={args.output}")
    finally:
        await registry.close_all()
        await embedding.close()
        await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
