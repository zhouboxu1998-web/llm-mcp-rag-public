from __future__ import annotations

import json
import re

from typing import Any

from .llm import LLMClient
from .models import QueryPlan


class QueryUnderstanding:
    def __init__(self, llm: LLMClient, enabled: bool = True, model: str | None = None) -> None:
        self.llm = llm
        self.enabled = enabled
        self.model = model

    @staticmethod
    def _fallback(query: str) -> QueryPlan:
        lowered = query.lower()
        needs_tools = bool(re.search(r"https?://|网页|网站|文件|读取|保存|创建|查询数据库|sqlite|sql", lowered))
        needs_knowledge = not bool(re.search(r"^(你好|hi|hello|谢谢|thanks)[!！。.? ]*$", lowered))
        return QueryPlan(
            original_query=query,
            normalized_query=query.strip(),
            knowledge_query=query.strip(),
            tool_query=query.strip(),
            needs_knowledge=needs_knowledge,
            needs_tools=needs_tools,
        )

    async def understand(self, query: str, model: str | None = None) -> QueryPlan:
        if not self.enabled:
            return self._fallback(query)

        system = (
            "You are a query router. Return ONLY valid JSON with keys: "
            "normalized_query, knowledge_query, tool_query, needs_knowledge, needs_tools. "
            "Do not add markdown. needs_knowledge and needs_tools must be booleans."
        )
        try:
            response = await self.llm.complete(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                model=model or self.model,
            )
        except Exception:
            return self._fallback(query)
        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
            data = json.loads(raw)
            return QueryPlan(
                original_query=query,
                normalized_query=str(data.get("normalized_query", query)).strip(),
                knowledge_query=str(data.get("knowledge_query", query)).strip(),
                tool_query=str(data.get("tool_query", query)).strip(),
                needs_knowledge=bool(data.get("needs_knowledge", True)),
                needs_tools=bool(data.get("needs_tools", True)),
            )
        except (ValueError, TypeError, json.JSONDecodeError):
            return self._fallback(query)
