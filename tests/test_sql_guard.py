"""SQL 守卫的单元测试：不需要 API key，也不需要启动 MCP 服务器。

    pip install -e ".[dev]"
    pytest -q
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers"))

import sql_guard  # noqa: E402

try:
    import sqlglot  # noqa: F401
    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False


def make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT);
        INSERT INTO customers VALUES (1, 'Acme Japan'), (2, 'Beta Works');
        INSERT INTO orders VALUES (101, 1, 'paid'), (102, 1, 'paid'), (103, 2, 'pending');
        """
    )
    conn.commit()
    return conn


class AuthorizerAndExecutionTests(unittest.TestCase):
    def test_select_returns_rows(self):
        result = sql_guard.execute_readonly(make_db(), "SELECT name FROM customers ORDER BY id", 100)
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["rows"][0]["name"], "Acme Japan")

    def test_join_and_aggregate_are_allowed(self):
        sql = "SELECT c.name, count(*) AS n FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.name ORDER BY c.name"
        result = sql_guard.execute_readonly(make_db(), sql, 100)
        self.assertEqual([r["n"] for r in result["rows"]], [2, 1])

    def test_row_cap(self):
        result = sql_guard.execute_readonly(make_db(), "SELECT * FROM orders", 2)
        self.assertEqual(result["row_count"], 2)

    def test_function_like_replace_is_allowed(self):
        result = sql_guard.execute_readonly(make_db(), "SELECT replace(name, 'Japan', 'JP') AS n FROM customers WHERE id = 1", 10)
        self.assertEqual(result["rows"][0]["n"], "Acme JP")

    def test_string_containing_keywords_is_allowed(self):
        result = sql_guard.execute_readonly(make_db(), "SELECT 'delete; drop' AS note", 10)
        self.assertEqual(result["rows"][0]["note"], "delete; drop")

    def test_writes_are_denied_by_authorizer(self):
        # 即使绕过 AST 校验直接交给 execute_readonly，authorizer 也会拒绝写操作
        for sql in (
            "WITH t AS (SELECT 1) SELECT * FROM t",  # 对照：合法
        ):
            sql_guard.execute_readonly(make_db(), sql, 10)
        for conn_sql in ("DELETE FROM orders", "INSERT INTO orders VALUES (9, 1, 'x')", "DROP TABLE orders"):
            conn = make_db()
            sql_guard.apply_authorizer(conn)
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(conn_sql)
            self.assertEqual(conn.execute("SELECT count(*) FROM orders").fetchone()[0], 3)

    def test_pragma_and_attach_are_denied(self):
        for sql in ("PRAGMA table_info(orders)", "ATTACH DATABASE ':memory:' AS x"):
            conn = make_db()
            sql_guard.apply_authorizer(conn)
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(sql)

    def test_write_inside_wrapper_is_rejected_with_value_error(self):
        with self.assertRaises(ValueError):
            sql_guard.execute_readonly(make_db(), "DELETE FROM orders", 10)


class ReadOnlyConnectionTests(unittest.TestCase):
    def test_mode_ro_blocks_writes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
            conn.close()
            ro = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("INSERT INTO t VALUES (1)")
            ro.close()


class TimeoutTests(unittest.TestCase):
    def test_runaway_recursive_query_is_interrupted(self):
        sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c"
        started = time.monotonic()
        with self.assertRaises(sql_guard.QueryTimeoutError):
            sql_guard.execute_readonly(make_db(), sql, 10, timeout_seconds=0.5)
        self.assertLess(time.monotonic() - started, 5)

    def test_fast_query_is_not_affected(self):
        result = sql_guard.execute_readonly(make_db(), "SELECT count(*) AS n FROM orders", 10, timeout_seconds=0.5)
        self.assertEqual(result["rows"][0]["n"], 3)


@unittest.skipUnless(HAS_SQLGLOT, "需要 pip install sqlglot")
class AstValidationTests(unittest.TestCase):
    def accepted(self, sql):
        sql_guard.validate_sql_ast(sql)

    def rejected(self, sql):
        with self.assertRaises(ValueError):
            sql_guard.validate_sql_ast(sql)

    def test_accepts_read_only_queries(self):
        self.accepted("SELECT name, region FROM customers")
        self.accepted("WITH t AS (SELECT * FROM orders) SELECT count(*) FROM t")
        self.accepted("SELECT id FROM orders UNION SELECT id FROM customers")
        self.accepted("SELECT * FROM (SELECT id FROM orders) AS sub")

    def test_accepts_what_the_old_regex_wrongly_blocked(self):
        self.accepted("SELECT 'delete later' AS note")
        self.accepted("SELECT replace(name, 'Japan', 'JP') FROM customers")
        self.accepted("SELECT 'a;b' AS x")

    def test_rejects_writes_and_ddl(self):
        self.rejected("DROP TABLE orders")
        self.rejected("DELETE FROM orders")
        self.rejected("INSERT INTO orders VALUES (1, 1, 'x')")
        self.rejected("UPDATE orders SET status = 'paid'")
        self.rejected("CREATE TABLE x (a INTEGER)")
        self.rejected("ALTER TABLE orders ADD COLUMN y TEXT")

    def test_rejects_write_hidden_in_cte(self):
        self.rejected("WITH t AS (SELECT 1) DELETE FROM orders")

    def test_rejects_multiple_statements(self):
        self.rejected("SELECT 1; DELETE FROM orders")

    def test_rejects_pragma_and_attach(self):
        self.rejected("PRAGMA table_info(orders)")
        self.rejected("ATTACH DATABASE 'x.db' AS x")

    def test_rejects_unparsable_empty_and_oversized(self):
        self.rejected("SELECT FROM WHERE ((")
        self.rejected("")
        self.rejected("SELECT 1 " + "+ 1 " * sql_guard.MAX_SQL_LENGTH)

    def test_rejects_dangerous_function(self):
        self.rejected("SELECT load_extension('evil')")


if __name__ == "__main__":
    unittest.main()
