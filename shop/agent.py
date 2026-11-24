from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from shop.config import Settings
from shop.database import Database
from shop.tools import ShopTools, TOOL_DEFINITIONS


SYSTEM_PROMPT = """
You are ShopBot, a helpful WhatsApp sales assistant for a retail business in India.

Your responsibilities:
- Answer product availability questions using list_products or search_products.
- Answer price questions using get_product_details or current catalogue results.
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


def _remove_unsupported_schema_fields(value: Any) -> Any:
    """Convert our provider-neutral JSON schema into Gemini-compatible JSON schema."""
    if isinstance(value, dict):
        # OpenAI's strict mode uses additionalProperties=false. Gemini function
        # declarations use parameters_json_schema, so omit that provider-specific key.
        return {
            key: _remove_unsupported_schema_fields(item)
            for key, item in value.items()
            if key != "additionalProperties"
        }
    if isinstance(value, list):
        return [_remove_unsupported_schema_fields(item) for item in value]
    return value


def build_gemini_tools() -> list[types.Tool]:
    """Translate the project's tool schemas into Google's function declarations."""
    declarations = []

    for definition in TOOL_DEFINITIONS:
        declarations.append(
            types.FunctionDeclaration(
                name=definition["name"],
                description=definition["description"],
                parameters_json_schema=_remove_unsupported_schema_fields(
                    definition["parameters"]
                ),
            )
        )

    return [types.Tool(function_declarations=declarations)]


class ShopAgent:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        self.max_iterations = settings.max_agent_iterations
        self.database = database
        self.tools = build_gemini_tools()

    def _generate(self, contents: list[types.Content]):
        return self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=self.tools,
                temperature=0.2,
            ),
        )

    @staticmethod
    def _text_content(role: str, text: str) -> types.Content:
        return types.Content(
            role=role,
            parts=[types.Part.from_text(text=text)],
        )

    def handle_message(self, customer_id: str, message: str) -> str:
        # Gemini's generate_content API receives the conversation as a list of
        # Content objects. We persist a compact user/model text history per customer.
        history = self.database.get_conversation_history(customer_id)
        contents = [
            self._text_content(entry["role"], entry["text"])
            for entry in history
            if entry.get("role") in {"user", "model"} and entry.get("text")
        ]
        contents.append(self._text_content("user", message))

        tool_runner = ShopTools(self.database, customer_id, message)
        response = self._generate(contents)

        # Agent loop: the model requests tools, Python executes them, and the
        # results are sent back to Gemini. Repeat until Gemini returns text.
        for iteration in range(self.max_iterations + 1):
            function_calls = response.function_calls or []

            if not function_calls:
                answer = response.text or (
                    "I couldn't generate a response. Could you rephrase that?"
                )
                updated_history = history + [
                    {"role": "user", "text": message},
                    {"role": "model", "text": answer},
                ]
                # Keep the most recent 20 messages (10 user/assistant turns).
                self.database.save_conversation_history(
                    customer_id, updated_history[-20:]
                )
                return answer

            if iteration == self.max_iterations:
                raise RuntimeError(
                    f"Agent exceeded its limit of {self.max_iterations} tool-calling iterations."
                )

            # Keep Gemini's original model content, including the function-call
            # parts and any model metadata required for the next tool response.
            if not response.candidates or not response.candidates[0].content:
                raise RuntimeError(
                    "Gemini requested a tool but returned no candidate content."
                )
            contents.append(response.candidates[0].content)

            function_response_parts = []
            for function_call in function_calls:
                tool_name = function_call.name
                arguments = dict(function_call.args or {})

                try:
                    result = tool_runner.dispatch(tool_name, arguments)
                except Exception as error:  # Return tool failures to the model as observations.
                    result = {"error": f"Tool execution failed: {error}"}

                print(f"  [tool] {tool_name}({arguments})")
                print(f"  [tool result] {result}")

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result},
                    )
                )

            contents.append(
                types.Content(
                    role="tool",
                    parts=function_response_parts,
                )
            )

            response = self._generate(contents)

    def close(self) -> None:
        """Release the SDK's HTTP resources when the application exits."""
        self.client.close()
