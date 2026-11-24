from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from shop.config import Settings


DEMO_PRODUCTS = [
    ("iPhone 16", 69900, 8),
    ("AirPods Pro", 24900, 15),
    ("USB-C Charger", 1999, 30),
    ("Wireless Mouse", 1299, 22),
    ("Mechanical Keyboard", 5499, 9),
]


class Database:
    def __init__(self, settings: Settings) -> None:
        self.path = Path(settings.database_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    price_rupees INTEGER NOT NULL CHECK(price_rupees >= 0),
                    stock INTEGER NOT NULL CHECK(stock >= 0)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    address_line TEXT NOT NULL,
                    locality TEXT NOT NULL,
                    city TEXT NOT NULL,
                    pincode TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('DRAFT', 'CONFIRMED')),
                    total_rupees INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL REFERENCES orders(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    unit_price_rupees INTEGER NOT NULL CHECK(unit_price_rupees >= 0)
                );

                CREATE TABLE IF NOT EXISTS customer_sessions (
                    customer_id TEXT PRIMARY KEY,
                    previous_response_id TEXT,
                    conversation_history TEXT NOT NULL DEFAULT '[]'
                );
                """
            )

            # Migrate an existing database created by the OpenAI version.
            # Keep previous_response_id so the existing database is not destructively changed.
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(customer_sessions)"
                ).fetchall()
            }
            if "conversation_history" not in columns:
                connection.execute(
                    "ALTER TABLE customer_sessions "
                    "ADD COLUMN conversation_history TEXT NOT NULL DEFAULT '[]'"
                )

            product_count = connection.execute(
                "SELECT COUNT(*) AS count FROM products"
            ).fetchone()["count"]

            if product_count == 0:
                connection.executemany(
                    "INSERT INTO products (name, price_rupees, stock) VALUES (?, ?, ?)",
                    DEMO_PRODUCTS,
                )

    def get_conversation_history(self, customer_id: str) -> list[dict[str, str]]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT conversation_history FROM customer_sessions WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()

        if row is None:
            return []

        try:
            history = json.loads(row["conversation_history"] or "[]")
        except json.JSONDecodeError:
            return []

        if not isinstance(history, list):
            return []

        # Ignore malformed records rather than breaking the customer's next message.
        return [
            entry
            for entry in history
            if isinstance(entry, dict)
            and entry.get("role") in {"user", "model"}
            and isinstance(entry.get("text"), str)
        ]

    def save_conversation_history(
        self, customer_id: str, history: list[dict[str, Any]]
    ) -> None:
        serialized_history = json.dumps(history, ensure_ascii=False)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO customer_sessions (customer_id, conversation_history)
                VALUES (?, ?)
                ON CONFLICT(customer_id)
                DO UPDATE SET conversation_history = excluded.conversation_history
                """,
                (customer_id, serialized_history),
            )
