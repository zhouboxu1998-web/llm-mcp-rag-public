from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

from dotenv import load_dotenv


load_dotenv()

def _json_escape(value: str) -> str:
    """把值转成可以安全放进 JSON 字符串里的片段（去掉外层引号）。"""
    return json.dumps(value, ensure_ascii=False)[1:-1]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    knowledge_dir: Path
    data_dir: Path
    mcp_config: Path
    sqlite_db: Path
    llm_model: str
    query_understanding_model: str
    llm_api_key: str
    llm_base_url: str | None
    embedding_model: str
    embedding_api_key: str
    embedding_base_url: str | None
    top_k_documents: int = 4
    top_k_tools: int = 5
    document_min_score: float = 0.20
    tool_min_score: float = 0.18
    query_understanding_enabled: bool = True
    max_tool_rounds: int = 8

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[1]

        def path_env(name: str, default: str) -> Path:
            value = Path(os.getenv(name, default))
            return value if value.is_absolute() else root / value

        return cls(
            project_root=root,
            knowledge_dir=path_env("KNOWLEDGE_DIR", "src/knowledge"),
            data_dir=path_env("DATA_DIR", "data"),
            mcp_config=path_env("MCP_CONFIG", "config/mcp_servers.json"),
            sqlite_db=path_env("SQLITE_DB", "data/demo.db"),
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
            query_understanding_model=os.getenv("QUERY_UNDERSTANDING_MODEL", os.getenv("LLM_MODEL", "deepseek-chat")),
            llm_api_key=os.getenv("OPENAI_API_KEY", ""),
            llm_base_url=os.getenv("OPENAI_BASE_URL"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
            embedding_api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL"),
            top_k_documents=int(os.getenv("TOP_K_DOCUMENTS", "4")),
            top_k_tools=int(os.getenv("TOP_K_TOOLS", "5")),
            document_min_score=float(os.getenv("DOCUMENT_MIN_SCORE", "0.20")),
            tool_min_score=float(os.getenv("TOOL_MIN_SCORE", "0.18")),
            query_understanding_enabled=os.getenv("QUERY_UNDERSTANDING_ENABLED", "true").lower() == "true",
            max_tool_rounds=int(os.getenv("MAX_TOOL_ROUNDS", "8")),
        )


def load_mcp_server_configs(settings: Settings) -> list[dict]:
    with settings.mcp_config.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    def esc(value: str) -> str:
        # 去掉 json.dumps 加上的外层引号
        return json.dumps(value, ensure_ascii=False)[1:-1]

    variables = {
        "PROJECT_ROOT": esc(str(settings.project_root)),
        "PYTHON": esc(sys.executable),
        "SQLITE_DB": esc(str(settings.sqlite_db)),
    }

    result: list[dict] = []
    for item in raw.get("servers", []):
        if not item.get("enabled", True):
            continue
        rendered = Template(json.dumps(item)).safe_substitute(variables)
        result.append(json.loads(rendered))
    return result
