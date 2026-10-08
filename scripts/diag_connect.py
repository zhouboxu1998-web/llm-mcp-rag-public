import argparse
import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from src.config import Settings, load_mcp_server_configs
from src.mcp_client import MCPClient


async def main():
    parser = argparse.ArgumentParser(description="逐个连接 MCP server 并列出工具")
    parser.add_argument("--timeout", type=float, default=90, help="每个 server 的握手超时（秒），首次下载 npx/uvx 包时可能较慢")
    args = parser.parse_args()

    load_dotenv()
    settings = Settings.from_env()
    configs = load_mcp_server_configs(settings)

    for item in configs:
        name = item["name"]
        print(f"\n>>> Connecting {name} ...  ({item['command']} {' '.join(item.get('args', []))})", flush=True)
        client = MCPClient(
            name=name,
            command=item["command"],
            args=item.get("args", []),
            env=item.get("env"),
            required=item.get("required", True),
        )
        started = time.perf_counter()
        try:
            tools = await asyncio.wait_for(client.connect(), timeout=args.timeout)
            elapsed = time.perf_counter() - started
            print(f"    OK ({elapsed:.2f}s) tools={[t.tool_name for t in tools]}", flush=True)
        except asyncio.TimeoutError:
            print(f"    TIMEOUT after {args.timeout:g}s -- server is not responding to handshake", flush=True)
        except Exception as exc:
            print(f"    ERROR: {type(exc).__name__}: {exc}", flush=True)
        finally:
            await client.close()


asyncio.run(main())