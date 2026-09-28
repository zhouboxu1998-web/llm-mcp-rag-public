from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VectorHit:
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolBinding:
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        return f"{self.server_name}__{self.tool_name}"

    @property
    def searchable_text(self) -> str:
        return (
            f"server: {self.server_name}\n"
            f"tool: {self.tool_name}\n"
            f"description: {self.description}\n"
            f"input_schema: {self.input_schema}"
        )


@dataclass(slots=True)
class QueryPlan:
    original_query: str
    normalized_query: str
    knowledge_query: str
    tool_query: str
    needs_knowledge: bool = True
    needs_tools: bool = True


@dataclass(slots=True)
class AgentResponse:
    answer: str
    query_plan: QueryPlan
    documents: list[VectorHit]
    tools: list[ToolBinding]
    rounds: int
    trace_id: str
    events: list[RuntimeEvent] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeEvent:
    trace_id: str
    event_type: str
    name: str
    started_at: float
    finished_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000
