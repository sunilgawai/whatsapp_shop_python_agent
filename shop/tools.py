from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any

from shop.database import Database


# Strict JSON schemas help the model produce arguments matching our Python tools.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "list_products",
        "description": "List every product in the shop with its current price and stock availability.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_products",
        "description": "Search the catalogue for products matching a customer's description or product name.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_product_details",
        "description": "Get the exact current price and stock for one product. Use this before quoting a price.",
        "parameters": {
            "type": "object",
            "properties": {"product_name": {"type": "string"}},
            "required": ["product_name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "prepare_order",
        "description": (
            "Create an order draft after the customer has selected products and provided a complete "
            "delivery address. This does NOT confirm or dispatch the order. If address details are missing, "
            "ask the customer instead of calling this tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_name": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1},
                        },
                        "required": ["product_name", "quantity"],
                        "additionalProperties": False,
                    },
                },
                "address_line": {"type": "string"},
                "locality": {"type": "string"},
                "city": {"type": "string"},
                "pincode": {"type": "string"},
            },
            "required": ["items", "address_line", "locality", "city", "pincode"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "confirm_order",
        "description": (
            "Confirm a previously prepared draft order ONLY when the customer's latest message clearly "
            "approves that order, for example 'yes, confirm the order' or 'please proceed'. Never use this "
            "for an ambiguous message. Confirmation records the order in this demo database; it does not "
            "physically ship anything."
        ),
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class ShopTools:
    def __init__(
        self,
        database: Database,
        customer_id: str,
        latest_user_message: str,
    ) -> None:
        self.database = database
        self.customer_id = customer_id
        self.latest_user_message = latest_user_message

    def list_products(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT name, price_rupees, stock FROM products ORDER BY name"
            ).fetchall()

        return {
            "products": [
                {
                    "name": row["name"],
                    "price_rupees": row["price_rupees"],
                    "stock": row["stock"],
                    "available": row["stock"] > 0,
                }
                for row in rows
            ]
        }

    def search_products(self, query: str) -> dict[str, Any]:
        term = f"%{query.strip()}%"
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT name, price_rupees, stock
                FROM products
                WHERE name LIKE ?
                ORDER BY name
                LIMIT 10
                """,
                (term,),
            ).fetchall()

        return {
            "matches": [
                {
                    "name": row["name"],
                    "price_rupees": row["price_rupees"],
                    "stock": row["stock"],
                    "available": row["stock"] > 0,
                }
                for row in rows
            ]
        }

    def get_product_details(self, product_name: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT name, price_rupees, stock FROM products WHERE name = ? COLLATE NOCASE",
                (product_name.strip(),),
            ).fetchone()

        if row is None:
            return {"found": False, "message": f"No exact product named '{product_name}' was found."}

        return {
            "found": True,
            "name": row["name"],
            "price_rupees": row["price_rupees"],
            "stock": row["stock"],
            "available": row["stock"] > 0,
        }

    def prepare_order(
        self,
        items: list[dict[str, Any]],
        address_line: str,
        locality: str,
        city: str,
        pincode: str,
    ) -> dict[str, Any]:
        if not items:
            return {"created": False, "reason": "The order has no items."}

        if not all(value.strip() for value in (address_line, locality, city, pincode)):
            return {
                "created": False,
                "reason": "A complete address is required: address line, locality, city and pincode.",
            }

        if not re.fullmatch(r"\d{6}", pincode.strip()):
            return {"created": False, "reason": "The Indian delivery pincode must contain exactly 6 digits."}

        if len(address_line.strip()) < 5 or len(locality.strip()) < 2:
            return {"created": False, "reason": "Please collect a more complete street address and locality."}

        requested: list[tuple[sqlite3.Row, int]] = []
        with self.database.connect() as connection:
            for item in items:
                quantity = item["quantity"]
                if quantity < 1 or quantity > 50:
                    return {"created": False, "reason": "Each item quantity must be between 1 and 50."}

                product = connection.execute(
                    "SELECT id, name, price_rupees, stock FROM products WHERE name = ? COLLATE NOCASE",
                    (item["product_name"].strip(),),
                ).fetchone()

                if product is None:
                    return {
                        "created": False,
                        "reason": f"Product '{item['product_name']}' was not found. Search for the correct product first.",
                    }

                if product["stock"] < quantity:
                    return {
                        "created": False,
                        "reason": (
                            f"Only {product['stock']} unit(s) of {product['name']} are currently available; "
                            f"the customer requested {quantity}. No order draft was created."
                        ),
                    }

                requested.append((product, quantity))

            total = sum(product["price_rupees"] * quantity for product, quantity in requested)
            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

            connection.execute(
                """
                INSERT INTO orders (
                    id, customer_id, address_line, locality, city, pincode, status, total_rupees
                ) VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', ?)
                """,
                (
                    order_id,
                    self.customer_id,
                    address_line.strip(),
                    locality.strip(),
                    city.strip(),
                    pincode.strip(),
                    total,
                ),
            )

            for product, quantity in requested:
                connection.execute(
                    """
                    INSERT INTO order_items (
                        order_id, product_id, product_name, quantity, unit_price_rupees
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (order_id, product["id"], product["name"], quantity, product["price_rupees"]),
                )

        return {
            "created": True,
            "order_id": order_id,
            "status": "DRAFT",
            "items": [
                {
                    "product": product["name"],
                    "quantity": quantity,
                    "unit_price_rupees": product["price_rupees"],
                    "line_total_rupees": product["price_rupees"] * quantity,
                }
                for product, quantity in requested
            ],
            "total_rupees": total,
            "delivery_address": {
                "address_line": address_line,
                "locality": locality,
                "city": city,
                "pincode": pincode,
            },
            "next_step": "Ask the customer to review the summary and explicitly confirm before confirming the order.",
        }

    def confirm_order(self, order_id: str) -> dict[str, Any]:
        # Server-side approval check: do not rely only on the LLM following instructions.
        approval_pattern = (
            r"^\s*(?:"
            r"yes|yes please|yes, please|"
            r"yes,?\s*(?:please\s*)?(?:confirm|proceed)(?:\s+this order)?|"
            r"confirm|confirm order|confirm this order|confirmed|please confirm|"
            r"please proceed|proceed|go ahead|place the order|place order"
            r")[.!\s]*$"
        )
        if not re.fullmatch(approval_pattern, self.latest_user_message, flags=re.IGNORECASE):
            return {
                "confirmed": False,
                "reason": "The customer's latest message does not contain clear order approval.",
            }

        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute(
                "SELECT id, status, total_rupees FROM orders WHERE id = ? AND customer_id = ?",
                (order_id, self.customer_id),
            ).fetchone()

            if order is None:
                return {"confirmed": False, "reason": "This order was not found for this customer."}

            if order["status"] != "DRAFT":
                return {"confirmed": False, "reason": f"Order is already {order['status']} and cannot be confirmed again."}

            latest_draft = connection.execute(
                """
                SELECT id FROM orders
                WHERE customer_id = ? AND status = 'DRAFT'
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (self.customer_id,),
            ).fetchone()
            if latest_draft is None or latest_draft["id"] != order_id:
                return {"confirmed": False, "reason": "Only the most recent draft order can be confirmed. Please review the latest order summary."}

            items = connection.execute(
                "SELECT product_id, product_name, quantity FROM order_items WHERE order_id = ?",
                (order_id,),
            ).fetchall()

            for item in items:
                product = connection.execute(
                    "SELECT stock FROM products WHERE id = ?",
                    (item["product_id"],),
                ).fetchone()
                if product is None or product["stock"] < item["quantity"]:
                    available = product["stock"] if product else 0
                    return {
                        "confirmed": False,
                        "reason": (
                            f"Stock changed after the draft was prepared. {item['product_name']} has "
                            f"{available} unit(s) available. Please prepare a new order."
                        ),
                    }

            for item in items:
                connection.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (item["quantity"], item["product_id"]),
                )

            connection.execute(
                "UPDATE orders SET status = 'CONFIRMED' WHERE id = ?",
                (order_id,),
            )

        return {
            "confirmed": True,
            "order_id": order_id,
            "status": "CONFIRMED",
            "total_rupees": order["total_rupees"],
            "message": "The order is confirmed in the demo database. No courier or physical dispatch has been triggered.",
        }

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "list_products": self.list_products,
            "search_products": self.search_products,
            "get_product_details": self.get_product_details,
            "prepare_order": self.prepare_order,
            "confirm_order": self.confirm_order,
        }

        handler = handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}

        try:
            return handler(**arguments)
        except (TypeError, ValueError, sqlite3.Error) as error:
            return {"error": f"Tool execution failed: {error}"}
