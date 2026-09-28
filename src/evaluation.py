from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from .models import ToolBinding, VectorHit


@dataclass(slots=True)
class RetrievalResult:
    query: str
    expected_tools: set[str]
    ranked_tools: list[str]
    hit_at_k: dict[int, bool]
    recall_at_k: dict[int, float]
    reciprocal_rank: float
    candidate_count: int
    estimated_tool_context_tokens: int


@dataclass(slots=True)
class AggregateMetrics:
    cases: int
    hit_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    mrr: float
    avg_candidate_count: float
    avg_context_tokens: float
    context_reduction_pct: float


def estimated_tokens_from_text(text: str) -> int:
    """Use a tokenizer-free estimate for relative prompt-size comparisons."""
    return max(1, (len(text) + 3) // 4)


def estimate_tool_context_tokens(tools: Iterable[ToolBinding]) -> int:
    payload = [
        {
            "name": tool.qualified_name,
            "description": tool.description,
            "parameters": tool.input_schema,
        }
        for tool in tools
    ]
    return estimated_tokens_from_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def evaluate_ranking(
    *,
    query: str,
    expected_tools: Sequence[str],
    ranked_hits: Sequence[VectorHit],
    ks: Sequence[int] = (1, 3, 5),
    candidate_count: int | None = None,
    context_tools: Sequence[ToolBinding] = (),
) -> RetrievalResult:
    expected = set(expected_tools)
    if not expected:
        raise ValueError(f"No expected tools available for evaluation query: {query}")
    ranked_names = [hit.document_id for hit in ranked_hits]
    first_relevant_rank = next(
        (index for index, name in enumerate(ranked_names, start=1) if name in expected),
        None,
    )
    reciprocal_rank = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank

    hit_at_k: dict[int, bool] = {}
    recall_at_k: dict[int, float] = {}
    for k in ks:
        top_k = ranked_names[:k]
        matched = len(set(top_k) & expected)
        hit_at_k[k] = matched > 0
        recall_at_k[k] = matched / max(1, len(expected))

    return RetrievalResult(
        query=query,
        expected_tools=expected,
        ranked_tools=ranked_names,
        hit_at_k=hit_at_k,
        recall_at_k=recall_at_k,
        reciprocal_rank=reciprocal_rank,
        candidate_count=candidate_count if candidate_count is not None else len(ranked_names),
        estimated_tool_context_tokens=estimate_tool_context_tokens(context_tools),
    )


def aggregate(results: Sequence[RetrievalResult], ks: Sequence[int]) -> AggregateMetrics:
    if not results:
        raise ValueError("No evaluation results")
    count = len(results)
    return AggregateMetrics(
        cases=count,
        hit_at_k={k: sum(result.hit_at_k[k] for result in results) / count for k in ks},
        recall_at_k={k: sum(result.recall_at_k[k] for result in results) / count for k in ks},
        mrr=sum(result.reciprocal_rank for result in results) / count,
        avg_candidate_count=sum(result.candidate_count for result in results) / count,
        avg_context_tokens=sum(result.estimated_tool_context_tokens for result in results) / count,
        context_reduction_pct=0.0,
    )


def compare_context_compression(all_tools: Sequence[ToolBinding], retrieved_tools: Sequence[ToolBinding]) -> float:
    baseline = estimate_tool_context_tokens(all_tools)
    if baseline <= 0:
        return 0.0
    selected = estimate_tool_context_tokens(retrieved_tools)
    return max(0.0, (baseline - selected) / baseline * 100)


def add_synthetic_tool_decoys(bindings: Sequence[ToolBinding], target_size: int) -> list[ToolBinding]:
    """Expand a tool catalog with unrelated tools for controlled scale experiments."""
    if target_size <= len(bindings):
        return list(bindings)
    categories = [
        ("calendar", "Create, list, update and delete calendar events"),
        ("email", "Search messages and send email notifications"),
        ("slack", "Search channels and post team messages"),
        ("github", "List issues, pull requests and repository metadata"),
        ("storage", "Upload, download and list objects in cloud storage"),
        ("crm", "Search customer records and account activities"),
        ("analytics", "Run predefined business analytics and KPI reports"),
        ("payments", "Look up invoices, refunds and payment status"),
    ]
    result = list(bindings)
    index = 0
    while len(result) < target_size:
        category, description = categories[index % len(categories)]
        tool_number = index // len(categories) + 1
        result.append(
            ToolBinding(
                server_name=f"synthetic_{category}",
                tool_name=f"action_{tool_number}",
                description=f"{description}; synthetic decoy tool #{tool_number}",
                input_schema={"type": "object", "properties": {}},
            )
        )
        index += 1
    return result
