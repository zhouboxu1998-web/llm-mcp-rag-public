import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
from src.config import Settings, load_mcp_server_configs
from src.mcp_client import MCPClient


async def main():
    load_dotenv()
    settings = Settings.from_env()
    configs = load_mcp_server_configs(settings)

    for item in configs:
        name = item["name"]
        print(f"\n>>> Connecting {name} ...", flush=True)
        client = MCPClient(
            name=name,
            command=item["command"],
            args=item.get("args", []),
            env=item.get("env"),
            required=item.get("required", True),
        )
        started = time.perf_counter()
        try:
            tools = await asyncio.wait_for(client.connect(), timeout=15)
            elapsed = time.perf_counter() - started
            print(f"    OK ({elapsed:.2f}s) tools={[t.tool_name for t in tools]}", flush=True)
        except asyncio.TimeoutError:
            print(f"    TIMEOUT after 15s -- server is not responding to handshake", flush=True)
        except Exception as exc:
            print(f"    ERROR: {type(exc).__name__}: {exc}", flush=True)
        finally:
            await client.close()


asyncio.run(main())