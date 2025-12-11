import json
import asyncio
from typing import Optional

from numpy.f2py.auxfuncs import throw_error

from MCPClient import MCPClient
from chat_openai import ChatOpenAI
from util import logTitle


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
        for client in self.mcp_client:
            await client.close()

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
                                logTitle("TOOL USE" + tool_call["function"]["name"])
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
        mcp_client = [MCPClient(name="fetch", command="uvx", args=["mcp-server-fetch"])]
        agent = Agent(mcp_client=mcp_client, model="deepseek-chat")
        await agent.init()
        res = await agent.invoke(prompt="请使用fetch工具，获取https://www.baidu.com的HTML源码")
        print(res)
    # 运行异步主函数
    asyncio.run(main())
