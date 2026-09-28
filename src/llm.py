from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from openai import AsyncOpenAI


@dataclass(slots=True)
class ToolCallDelta:
    id: str
    name: str
    arguments: str


@dataclass(slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCallDelta] = field(default_factory=list)


class LLMClient:
    def __init__(self, api_key: str, base_url: str | None, model: str, temperature: float = 0.0) -> None:
        from openai import AsyncOpenAI

        self.client: AsyncOpenAI = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        stream = await self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            tools=tools or None,
            temperature=self.temperature,
            stream=True,
        )

        content_parts: list[str] = []
        tool_calls: dict[int, dict[str, str]] = {}
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
            if delta.tool_calls:
                for tool_delta in delta.tool_calls:
                    slot = tool_calls.setdefault(
                        tool_delta.index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if tool_delta.id:
                        slot["id"] = tool_delta.id
                    if tool_delta.function:
                        if tool_delta.function.name:
                            slot["name"] = tool_delta.function.name
                        if tool_delta.function.arguments:
                            slot["arguments"] += tool_delta.function.arguments

        return LLMResponse(
            content="".join(content_parts),
            tool_calls=[ToolCallDelta(**tool_calls[index]) for index in sorted(tool_calls)],
        )

    async def stream_text(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def close(self) -> None:
        await self.client.close()


def tool_definition(binding) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": binding.qualified_name,
            "description": binding.description,
            "parameters": binding.input_schema,
        },
    }


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Tool arguments must be a JSON object")
    return value
