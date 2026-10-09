from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

from mcp.server import MCPServer

try:
    import sqlglot  # noqa: F401  AST 校验依赖；缺失时拒绝启动，而不是悄悄放行
except ImportError:
    sys.exit("sqlglot is required for SQL AST validation. Run: pip install -e .")

import sql_guard

QUERY_TIMEOUT_SECONDS = float(os.getenv("SQL_TIMEOUT_SECONDS", sql_guard.DEFAULT_TIMEOUT_SECONDS))

db_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (Path(__file__).resolve().parents[1] / "data" / "demo.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

mcp = MCPServer("sqlite")


def connect() -> sqlite3.Connection:
    # URI mode=ro prevents accidental database creation or writes.
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)


@mcp.tool()
def list_tables() -> list[str]:
    """List user tables in the read-only SQLite database."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]


@mcp.tool()
def describe_table(table_name: str) -> list[dict]:
    """Return column metadata for a user table."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("Invalid table name")
    with connect() as conn:
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [
        {"cid": row[0], "name": row[1], "type": row[2], "notnull": row[3], "default": row[4], "pk": row[5]}
        for row in rows
    ]


@mcp.tool()
def query(sql: str, max_rows: int = 100) -> dict:
    """Execute one read-only SELECT/CTE query (AST-validated, time-limited) and cap the returned rows."""
    sql = sql.strip().rstrip(";").strip()
    sql_guard.validate_sql_ast(sql)
    max_rows = max(1, min(max_rows, 500))
    conn = connect()
    try:
        return sql_guard.execute_readonly(conn, sql, max_rows, QUERY_TIMEOUT_SECONDS)
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run("stdio")
