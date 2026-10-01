from __future__ import annotations

import asyncio
import os

from rich.console import Console

from .bootstrap import Application
from .config import Settings


console = Console()


async def async_main() -> None:
    settings = Settings.from_env()
    # 固定工作目录：Agent 通过文件工具写出的相对路径文件，始终落在项目根目录，
    # 而不是取决于从哪个目录（如 PyCharm 的 src/）启动。
    os.chdir(settings.project_root)
    app = Application(settings)
    await app.startup()
    try:
        console.print("[bold green]MCP-RAG Agent ready.[/bold green]")
        console.print("输入 exit 退出。")
        while True:
            prompt = input("\nUser> ").strip()
            if prompt.lower() in {"exit", "quit"}:
                break
            result = await app.invoke(prompt)
            console.print(f"\n[bold cyan]Answer[/bold cyan]\n{result.answer}")
            console.print(f"[dim]trace={result.trace_id} rounds={result.rounds} docs={len(result.documents)} tools={len(result.tools)}[/dim]")
    finally:
        await app.shutdown()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
