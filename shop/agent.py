from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from shop.config import Settings
from shop.database import Database
from shop.tools import ShopTools, TOOL_DEFINITIONS


SYSTEM_PROMPT = """
You are ShopBot, a helpful WhatsApp sales assistant for a retail business in India.

Your responsibilities:
- Answer product availability questions using list_products or search_products.
- Answer price questions using get_product_details or the current catalogue results.
- Help customers prepare an order using prepare_order.
- Confirm an order only after the customer clearly approves the exact draft order.

Business rules:
1. Never invent product names, prices, stock levels, discounts, delivery fees, or order statuses.
   Use the catalogue tools as the source of truth.
2. Use INR and format prices as ₹ with comma separators.
3. If a product name is ambiguous, ask a short follow-up question or search the catalogue.
4. Before preparing an order, collect each product and quantity plus a complete delivery address:
   address line/building, locality, city, and 6-digit Indian pincode. A city name such as 'Pune'
   alone is not a complete delivery address.
5. When all information is available, call prepare_order. It only creates a DRAFT.
6. Present the draft order ID, each item, quantities, prices, total, and delivery address. Ask the
   customer to explicitly confirm it.
7. Do not call confirm_order based on the customer's original request to 'send' or 'prepare' items.
   Wait for a separate, clear approval after showing the order summary.
8. If the customer says something ambiguous such as 'okay' without a clear reference to the order,
   ask whether they want to confirm the displayed order.
9. Confirming in this demo only marks the order CONFIRMED and reduces local demo stock. It does not
   take payment, book a courier, or physically dispatch products. Never claim that a package has shipped.
10. Keep WhatsApp replies concise, friendly, and easy to read. Ask only for the missing information.
""".strip()


class ShopAgent:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.max_iterations = settings.max_agent_iterations
        self.database = database

    def handle_message(self, customer_id: str, message: str) -> str:
        previous_response_id = self.database.get_previous_response_id(customer_id)
        tool_runner = ShopTools(self.database, customer_id, message)

        request: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM_PROMPT,
            "tools": TOOL_DEFINITIONS,
            "input": [{"role": "user", "content": message}],
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        response = self.client.responses.create(**request)

        # This is the agent loop: execute each requested tool, return its output to the
        # model, and repeat until the model produces a normal text answer.
        for _ in range(self.max_iterations):
            function_calls = [
                item for item in response.output if item.type == "function_call"
            ]

            if not function_calls:
                self.database.save_previous_response_id(customer_id, response.id)
                return response.output_text or "I couldn't generate a response. Could you rephrase that?"

            tool_outputs = []
            for call in function_calls:
                try:
                    arguments = json.loads(call.arguments)
                    result = tool_runner.dispatch(call.name, arguments)
                except json.JSONDecodeError:
                    result = {"error": "The model supplied invalid JSON tool arguments."}

                print(f"  [tool] {call.name}({call.arguments})")
                print(f"  [tool result] {result}")

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            response = self.client.responses.create(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                previous_response_id=response.id,
                input=tool_outputs,
            )

        raise RuntimeError(
            f"Agent exceeded its limit of {self.max_iterations} iterations."
        )
