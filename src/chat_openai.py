import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import List

import openai
from click import prompt
from dotenv import load_dotenv
from langchain_core.messages.tool import tool_call
from mcp import Tool
from openai import OpenAI, responses
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from util import logTitle

load_dotenv()


@dataclass
class FunctionCall:
    """函数调用信息 - arguments 为字符串类型"""
    name: str
    arguments: str  # JSON 字符串格式的参数


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    function: FunctionCall


@dataclass
class ChatOpenAI:
    def __init__(self, model_name: str, tools=[], system_prompt: str = "", context: str = ""):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = model_name
        self.tools = tools
        self.system_prompt = system_prompt
        self.context = context
        self.llm = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.message = []
        if self.system_prompt:
            self.message.append({"role": "system", "content": self.system_prompt, })
        if self.context:
            self.message.append({"role": "user", "content": self.context, }
                                )

    async def chat(self, prompt: str):
        logTitle("CHAT")
        if prompt:
            self.message.append({"role": "user", "content": prompt, })
            stream = self.llm.chat.completions.create(
                model=self.model,
                messages=self.message,
                tools=self.getToolsDefinition(),
                stream=True,
            )

        content = ""
        # 定义 ToolCall 列表类型
        tool_calls_list = []
        logTitle("RESPONSE")
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                content_chunk = delta.content if delta.content else ""
                content += content_chunk
                sys.stdout.write(content_chunk)
            if delta.tool_calls:
                for tool_call_chunk in delta.tool_calls:
                    if len(tool_calls_list) <= tool_call_chunk.index:
                        tool_calls_list.append({"id": "", "function": {"name": "", "arguments": ""}})
                    current_call = tool_calls_list[tool_call_chunk.index]
                    if tool_call_chunk.id:
                        current_call["id"] += tool_call_chunk.id
                    if tool_call_chunk.function.name:
                        current_call["function"]["name"] += tool_call_chunk.function.name
                    if tool_call_chunk.function.arguments:
                        current_call["function"]["arguments"] += tool_call_chunk.function.arguments
        self.message.append({"role": "assistant",
                             "content": content,
                             "tool_calls": [{"id": call["id"],
                                             "type": "function",
                                             "function": call["function"]}
                                            for call in tool_calls_list]
                             if tool_calls_list else None
                             })
        return {
            "content": content,
            "tool_call": tool_calls_list
        }

    def appendToolResult(self, tool_call_id: str, tool_result: str):
        self.message.append({"role": "tool",
                             "tool_call_id": tool_call_id,
                             "content": tool_result
                             })

    def getToolsDefinition(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool['name'],
                    "description": tool['description'],
                    "parameters": tool['inputSchema']
                }
            } for tool in self.tools
        ]


if __name__ == "__main__":
        prompt = "nihao"
        llm = ChatOpenAI("deepseek-chat")
        res = asyncio.run(llm.chat(prompt=prompt))
        print(res)
