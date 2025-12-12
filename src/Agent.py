import json
import asyncio
import os
from typing import Optional

from numpy.f2py.auxfuncs import throw_error

from MCPClient import MCPClient
from ChatOpenai import ChatOpenAI
from Util import logTitle


class Agent:
    def __init__(self, mcp_client: list[MCPClient], model: str, prompt: str = "", context: str = ""):
        self.mcp_client = mcp_client
        self.llm: Optional[ChatOpenAI] = None
        self.model = model
        self.prompt = prompt
        self.context = context

    async def init(self):
        logTitle("INIT LLM AND TOOLS")
        tools_arr = []
        for client in self.mcp_client:
            await client.init()
            tools_arr.extend(client.get_tools())
            self.llm = ChatOpenAI(model=self.model, system_prompt=self.prompt, context=self.context, tools=tools_arr)

    async def close(self):
        print()
        logTitle("CLOSE MCP CLIENT")
        for client in self.mcp_client:
            try:
                await client.close()
            except Exception as e:
                print(f"关闭客户端时出现异常: {e}")
                # 忽略关闭时的异常，继续关闭其他客户端

    async def invoke(self, prompt: str):
        if self.llm is None: throw_error("LLM not initialized")
        res = await self.llm.chat(prompt=prompt)
        while True:
            # 处理工具调用
            if len(res["tool_calls"]) > 0:
                for tool_call in res["tool_calls"]:
                    # 根据tool_call的name在mcpclient的tools中寻找对应的工具
                    for mcp_client in self.mcp_client:
                        for tool in mcp_client.tools:
                            if tool["name"] == tool_call["function"]["name"]:
                                print()
                                logTitle("TOOL USE: " + tool_call["function"]["name"])
                                print("工具调用:", tool_call["function"]["name"],
                                      "调用参数:", tool_call["function"]["arguments"])
                                # 调用工具
                                tool_result = await mcp_client.call_tool(tool["name"],
                                                    json.loads(tool_call["function"]["arguments"]))
                                print("工具执行结果:", tool_result)
                                # 将工具执行结果添加到消息历史
                                self.llm.appendToolResult(tool_call["id"], str(tool_result))
                                break
                        else:
                            continue
                        break
                    else:
                        self.llm.appendToolResult(tool_call["id"], "工具未找到")
                # 重新调用LLM
                res = await self.llm.chat()
                continue
            else:
                await self.close()
                return res


if __name__ == "__main__":
    async def main():
        current_dir = os.getcwd()
        file_mcp = MCPClient(name="file", command="npx", args=["-y",
        "@modelcontextprotocol/server-filesystem", current_dir])
        fetch_mcp = MCPClient(name="fetch", command="uvx", args=["mcp-server-fetch"])
        agent = Agent(mcp_client=[file_mcp, fetch_mcp], model="deepseek-chat")
        await agent.init()
        res = await agent.invoke(prompt=f"请使用fetch工具，获取https://www.baidu.com的HTML源码,并总结后保存到{current_dir}的fetch.md文件中")
        print(res)
    # 运行异步主函数
    asyncio.run(main())
