from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

from llm_mcp_rag.config import Settings, load_mcp_server_configs
from llm_mcp_rag.embeddings import EmbeddingClient
from llm_mcp_rag.evaluation import add_synthetic_tool_decoys, aggregate, estimate_tool_context_tokens, evaluate_ranking
from llm_mcp_rag.models import ToolBinding, VectorHit
from llm_mcp_rag.tool_retriever import ToolRetriever

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "tool_retrieval_cases.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare all-tools context against semantic Top-K MCP tool retrieval."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=Path("data/tool_retrieval_benchmark.json"))
    parser.add_argument("--ks", nargs="+", type=int, default=[1, 3, 5])
    parser.add_argument("--min-score", type=float, default=-1.0)
    parser.add_argument("--scale", nargs="*", type=int, default=[], help="Optional catalog sizes, e.g. 20 50 100, using synthetic decoys")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


async def discover_tools(settings: Settings):
    from llm_mcp_rag.mcp_client import MCPClient
    from llm_mcp_rag.mcp_registry import MCPRegistry

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



def resolve_expected_names(expected: list[str], available: set[str]) -> list[str]:
    """Drop stale expected names so the benchmark reports missing server capabilities explicitly."""
    return [name for name in expected if name in available]


async def run_catalog_benchmark(
    *,
    settings: Settings,
    embedding: EmbeddingClient,
    base_bindings: list[ToolBinding],
    cases: list[dict],
    args: argparse.Namespace,
    output_dir: Path,
) -> dict:
    bindings = base_bindings
    retriever = ToolRetriever(embedding, settings.data_dir)
    await retriever.build(bindings)
    available = {tool.qualified_name for tool in bindings}
    all_context_tokens = estimate_tool_context_tokens(bindings)

    results = []
    case_records = []
    retrieval_latency_ms = []
    for case in cases:
        expected = resolve_expected_names(case["expected_tools"], available)
        if not expected:
            case_records.append({
                "query": case["query"],
                "expected_tools": case["expected_tools"],
                "missing_expected_tools": case["expected_tools"],
                "skipped": True,
                "reason": "none of the expected tool names are present in the discovered catalog",
            })
            continue

        started = time.perf_counter()
        hits = await retriever.retrieve_hits(case["query"], max(args.ks), args.min_score)
        retrieval_latency_ms.append((time.perf_counter() - started) * 1000)
        selected_tools = [retriever.bindings[hit.document_id] for hit in hits]
        result = evaluate_ranking(
            query=case["query"],
            expected_tools=expected,
            ranked_hits=hits,
            ks=args.ks,
            candidate_count=len(selected_tools),
            context_tools=selected_tools,
        )
        results.append(result)
        missing = sorted(set(case["expected_tools"]) - available)
        case_records.append({
            "query": result.query,
            "expected_tools": sorted(result.expected_tools),
            "missing_expected_tools": missing,
            "ranked_tools": result.ranked_tools,
            "hit_at_k": result.hit_at_k,
            "recall_at_k": result.recall_at_k,
            "reciprocal_rank": result.reciprocal_rank,
            "candidate_count": result.candidate_count,
            "estimated_tool_context_tokens": result.estimated_tool_context_tokens,
            "estimated_context_reduction_pct": max(
                0.0,
                1.0 - result.estimated_tool_context_tokens / all_context_tokens,
            ) * 100.0 if all_context_tokens else 0.0,
        })

    if not results:
        raise RuntimeError("No benchmark cases matched the discovered tool catalog")

    metrics = aggregate(results, args.ks)
    metrics.context_reduction_pct = (
        max(0.0, 1.0 - metrics.avg_context_tokens / all_context_tokens) * 100.0
        if all_context_tokens
        else 0.0
    )
    return {
        "tool_count": len(bindings),
        "all_tools_context_tokens_est": all_context_tokens,
        "baseline": {
            "tool_coverage": 1.0,
            "context_tokens_est": all_context_tokens,
            "candidate_count": len(bindings),
        },
        "semantic_top_k": {
            "cases": metrics.cases,
            "hit_at_k": metrics.hit_at_k,
            "recall_at_k": metrics.recall_at_k,
            "mrr": metrics.mrr,
            "avg_candidate_count": metrics.avg_candidate_count,
            "avg_context_tokens_est": metrics.avg_context_tokens,
            "context_reduction_pct": metrics.context_reduction_pct,
            "avg_retrieval_latency_ms": sum(retrieval_latency_ms) / len(retrieval_latency_ms),
        },
        "cases": case_records,
    }


async def main() -> None:
    args = parse_args()
    load_dotenv()
    settings = Settings.from_env()
    args.ks = tuple(sorted({k for k in args.ks if k > 0}))
    if not args.ks:
        raise ValueError("At least one positive --ks value is required")

    embedding = EmbeddingClient(
        settings.embedding_api_key,
        settings.embedding_base_url,
        settings.embedding_model,
    )
    registry, base_bindings = await discover_tools(settings)

    try:
        cases = load_cases(args.cases)
        catalogs = [len(base_bindings)]
        catalogs.extend(size for size in sorted(set(args.scale)) if size > len(base_bindings))
        reports = []
        for target_size in catalogs:
            bindings = add_synthetic_tool_decoys(base_bindings, target_size)
            reports.append(
                await run_catalog_benchmark(
                    settings=settings,
                    embedding=embedding,
                    base_bindings=bindings,
                    cases=cases,
                    args=args,
                    output_dir=args.output.parent,
                )
            )

        payload = {
            "methodology": {
                "retrieval": "cosine similarity over MCP tool metadata embeddings",
                "baseline": "all discovered MCP tools are available to the model; baseline has full coverage but no ranking metric",
                "token_estimator": "UTF-8 JSON characters / 4, used only for relative comparison",
                "top_k_metrics": [f"Hit@{k}" for k in args.ks] + [f"Recall@{k}" for k in args.ks] + ["MRR"],
            },
            "catalog_benchmarks": reports,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print("=== MCP Tool Retrieval Benchmark ===")
        for report in reports:
            print(f"\nCatalog tools={report['tool_count']}")
            print(f"All-tools context={report['baseline']['context_tokens_est']} est. tokens")
            topk = report["semantic_top_k"]
            for k in args.ks:
                print(
                    f"Top-{k}: Hit@{k}={topk['hit_at_k'][k]:.2%} "
                    f"Recall@{k}={topk['recall_at_k'][k]:.2%}"
                )
            print(f"MRR={topk['mrr']:.4f}")
            print(f"avg_candidates={topk['avg_candidate_count']:.2f}")
            print(f"avg_context_tokens={topk['avg_context_tokens_est']:.2f}")
            print(f"context_reduction={topk['context_reduction_pct']:.2f}%")
            print(f"avg_retrieval_latency={topk['avg_retrieval_latency_ms']:.2f} ms")
        print(f"report={args.output}")
    finally:
        await registry.close_all()
        await embedding.close()


if __name__ == "__main__":
    asyncio.run(main())
