"""SQL 安全守卫，供 SQLite MCP Server 使用。

不依赖 mcp 包，便于单元测试。四层防御各自独立，任何一层失效，其余层仍能阻止写入：

1. AST 校验（sqlglot）：先把 SQL 解析成语法树，只允许单条 SELECT / UNION 查询；
   语法树中任何位置出现 INSERT / UPDATE / DELETE / DDL / PRAGMA / ATTACH 等节点都会被拒绝
   （包括夹在 CTE 里的写操作）。
2. SQLite authorizer：SQLite 在编译语句时，对每个操作回调一次；这里只放行读操作，
   其余一律拒绝。
3. 只读连接：由服务器用 ``mode=ro`` 打开数据库，数据库层面禁止写入。
4. 执行超时：用 progress handler 在超时后中断查询，避免失控查询（如无限递归 CTE）占满进程。
"""
from __future__ import annotations

import sqlite3
import time

MAX_SQL_LENGTH = 10_000
DEFAULT_TIMEOUT_SECONDS = 5.0

# SQLite authorizer 动作码（用 getattr 兜底，兼容不同 Python 版本的常量导出）
_SELECT = getattr(sqlite3, "SQLITE_SELECT", 21)
_READ = getattr(sqlite3, "SQLITE_READ", 20)
_FUNCTION = getattr(sqlite3, "SQLITE_FUNCTION", 31)
_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)
_OK = getattr(sqlite3, "SQLITE_OK", 0)
_DENY = getattr(sqlite3, "SQLITE_DENY", 1)

_BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit"}

# 语法树中不允许出现的节点类型（按名称查找，兼容不同 sqlglot 版本中不存在的名称）
_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
    "TruncateTable", "Command", "Pragma", "Attach", "Detach", "Transaction",
    "Commit", "Rollback", "Set", "Use", "Copy",
)
# 语法树根节点允许的类型：查询语句本身
_ROOT_NODE_NAMES = ("Select", "Union", "Intersect", "Except", "SetOperation", "Subquery")


class QueryTimeoutError(ValueError):
    """查询超过允许的执行时间。"""


def _types(exp, names: tuple[str, ...]) -> tuple[type, ...]:
    return tuple(getattr(exp, name) for name in names if hasattr(exp, name))


def validate_sql_ast(sql: str) -> None:
    """用 sqlglot 解析 SQL，不满足只读单条查询时抛出 ValueError。"""
    import sqlglot
    from sqlglot import exp
    from sqlglot.errors import SqlglotError

    if not sql or not sql.strip():
        raise ValueError("SQL is empty")
    if len(sql) > MAX_SQL_LENGTH:
        raise ValueError(f"SQL is longer than {MAX_SQL_LENGTH} characters")

    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except SqlglotError as exc:
        raise ValueError(f"SQL cannot be parsed: {exc}") from exc

    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is allowed")

    root = statements[0]
    if not isinstance(root, _types(exp, _ROOT_NODE_NAMES)):
        raise ValueError(f"Only SELECT queries are allowed (got {type(root).__name__})")

    forbidden = _types(exp, _FORBIDDEN_NODE_NAMES)
    bad = root.find(*forbidden) if forbidden else None
    if bad is not None:
        raise ValueError(f"Forbidden SQL construct: {type(bad).__name__}")

    for func in root.find_all(exp.Anonymous):
        if str(func.name).lower() in _BLOCKED_FUNCTIONS:
            raise ValueError(f"Forbidden SQL function: {func.name}")


def apply_authorizer(conn: sqlite3.Connection) -> None:
    """只放行读操作：SELECT / READ / RECURSIVE，以及不在黑名单中的函数。"""

    def authorizer(action, arg1, arg2, db_name, source):  # noqa: ANN001
        if action in (_SELECT, _READ, _RECURSIVE):
            return _OK
        if action == _FUNCTION:
            return _DENY if str(arg2 or "").lower() in _BLOCKED_FUNCTIONS else _OK
        return _DENY

    conn.set_authorizer(authorizer)


def apply_timeout(conn: sqlite3.Connection, seconds: float) -> None:
    """超过 seconds 秒后中断正在执行的查询。"""
    deadline = time.monotonic() + seconds
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)


def execute_readonly(
    conn: sqlite3.Connection,
    sql: str,
    max_rows: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """在 authorizer + 超时保护下执行查询，并限制返回行数。"""
    apply_authorizer(conn)
    apply_timeout(conn, timeout_seconds)
    try:
        cursor = conn.execute(f"SELECT * FROM ({sql}) LIMIT {int(max_rows)}")
        columns = [column[0] for column in cursor.description or []]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower():
            raise QueryTimeoutError(f"Query exceeded the {timeout_seconds:g}s time limit") from exc
        raise ValueError(f"SQL failed: {exc}") from exc
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"SQL rejected: {exc}") from exc
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
