from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

from llm_mcp_rag.embeddings import EmbeddingClient
from llm_mcp_rag.models import ToolBinding
from llm_mcp_rag.tool_retriever import ToolRetriever


CASES = [
    ("读取文件内容并保存到另一个文件", {"file__read_file", "file__write_file"}),
    ("访问网页并获取 HTML", {"fetch__fetch"}),
    ("查询 SQLite 中有哪些表", {"sqlite__list_tables"}),
]


async def main() -> None:
    load_dotenv()
    client = EmbeddingClient(
        os.environ.get("EMBEDDING_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
        os.environ.get("EMBEDDING_BASE_URL") or os.environ.get("OPENAI_BASE_URL"),
        os.environ.get("EMBEDDING_MODEL", "text-embedding-v4"),
    )
    retriever = ToolRetriever(client)
    bindings = [
        ToolBinding("file", "read_file", "Read the contents of a file", {"type": "object"}),
        ToolBinding("file", "write_file", "Write text content to a file", {"type": "object"}),
        ToolBinding("fetch", "fetch", "Fetch a web page and return its content", {"type": "object"}),
        ToolBinding("sqlite", "list_tables", "List database tables", {"type": "object"}),
        ToolBinding("sqlite", "query", "Run a read-only SQL query", {"type": "object"}),
    ]
    await retriever.build(bindings)

    correct = 0
    for query, expected in CASES:
        hits = await retriever.retrieve(query, k=3, min_score=-1)
        names = {hit.qualified_name for hit in hits}
        ok = bool(names & expected)
        correct += int(ok)
        print(f"query={query}\nhits={names}\npass={ok}\n")

    print(f"retrieval_hit_rate={correct / len(CASES):.2%}")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
