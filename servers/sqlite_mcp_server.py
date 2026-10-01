from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

from mcp.server import MCPServer


READONLY_SQL = re.compile(r"^\s*(select|with|pragma\s+table_info|pragma\s+database_list)\b", re.I)
BLOCKED_SQL = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum|reindex)\b", re.I)

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
    """Execute one read-only SELECT/CTE query and cap the number of returned rows."""
    sql = sql.strip().rstrip(";")
    if not READONLY_SQL.match(sql) or BLOCKED_SQL.search(sql):
        raise ValueError("Only read-only SELECT/CTE/limited PRAGMA statements are allowed")
    if ";" in sql:
        raise ValueError("Multiple SQL statements are not allowed")
    max_rows = max(1, min(max_rows, 500))
    with connect() as conn:
        cursor = conn.execute(f"SELECT * FROM ({sql}) LIMIT {max_rows}")
        columns = [column[0] for column in cursor.description or []]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


if __name__ == "__main__":
    mcp.run("stdio")
