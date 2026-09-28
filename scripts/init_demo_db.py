from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path("data/demo.db")
DB.parent.mkdir(exist_ok=True)

with sqlite3.connect(DB) as conn:
    conn.executescript(
        """
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;
        CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, region TEXT);
        CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);
        CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, status TEXT);
        CREATE TABLE order_items(order_id INTEGER, product_id INTEGER, quantity INTEGER);
        INSERT INTO customers VALUES
          (1, 'Acme Japan', 'Kanto'),
          (2, 'Beta Works', 'Kansai'),
          (3, 'Gamma Systems', 'Chubu');
        INSERT INTO products VALUES
          (1, 'Pressure Sensor', 'Sensor', 1200.0),
          (2, 'Vision Module', 'Inspection', 3500.0),
          (3, 'Maintenance Kit', 'Service', 800.0);
        INSERT INTO orders VALUES
          (101, 1, '2026-09-01', 'paid'),
          (102, 1, '2026-09-08', 'paid'),
          (103, 2, '2026-09-10', 'pending'),
          (104, 3, '2026-09-12', 'paid');
        INSERT INTO order_items VALUES
          (101, 1, 10), (101, 2, 2), (102, 3, 5), (103, 2, 1), (104, 1, 4);
        """
    )

print(DB)
