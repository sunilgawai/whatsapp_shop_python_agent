# ShopBot — WhatsApp AI Sales Assistant (Gemini learning MVP)

A small Python project that demonstrates an LLM agent loop for a retail business. It uses Google's Gemini Developer API through the official `google-genai` Python SDK.

## What it can do

- List products and current stock from SQLite.
- Search for a product and retrieve its price.
- Prepare an order draft after collecting product quantities and a complete address.
- Confirm a draft only after a clear approval in the customer's latest message.
- Keep a short conversation history per customer in SQLite.

## Safety and scope

This is a local learning MVP. Confirmation updates a local SQLite order and stock record only. It does **not** accept payment, book a courier, or dispatch a package. Do not connect it to a live shop or real customer data until authentication, webhook verification, idempotency, monitoring, privacy controls, and business-specific order rules are added.

The product names, prices, and stock in `shop/database.py` are demo data only. Replace them with a read-only adapter to the actual CMS before using real catalogue information.

## Requirements

- Python 3.9 or later
- A Gemini API key from Google AI Studio
- Access to the selected Gemini model under your Google AI Studio account

The default model is `gemini-3.8-flash`. Google's Gemini Developer API pricing page currently lists free-tier access for selected models, but the free tier has rate limits and model availability can vary. It is not unlimited. Check the current [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) before relying on it. On the free tier, Google says submitted content may be used to improve its products; review Google's terms before using customer or business data.

## Setup (macOS/Linux)

```bash
cd whatsapp_shop_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then open `.env` and set:

```env
GEMINI_API_KEY=your_actual_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
```

You do not need an OpenAI API key or the OpenAI Python package for this version.

Run:

```bash
python main.py
```

Try these messages in one session:

1. `What products are available?`
2. `What is the price of AirPods Pro?`
3. `I want 2 AirPods Pro and 1 USB-C Charger. Send them to Pune.`
4. When asked for details, provide a complete demo address, e.g. `Flat 12, Sunshine Apartments, Baner Road, Baner, Pune, Maharashtra 411045`.
5. Review the draft and reply `Yes, confirm this order.`

The demo asks for address line, locality, city, and a six-digit pincode as separate fields. It may interpret a natural-language address into those fields; review the order summary before confirming.

## Project layout

```text
whatsapp_shop_agent/
├── main.py              # Terminal chat loop (temporary WhatsApp stand-in)
├── requirements.txt
├── .env.example
└── shop/
    ├── config.py        # Gemini/API environment settings
    ├── database.py      # SQLite schema, sample catalogue, session history
    ├── tools.py         # Business tools the model can call
    └── agent.py          # Gemini function calling + agent loop
```

## How the Gemini agent loop works

1. `ShopAgent` sends the customer's message, system instructions, and Gemini function declarations to the model.
2. Gemini either returns final text or one or more function calls.
3. `ShopTools.dispatch()` routes each function call to a Python business function.
4. The application sends function responses back to Gemini as tool-role content.
5. Gemini can request more tools or return a final answer. The loop has a maximum iteration limit.
6. The application saves a compact user/model conversation history per customer in SQLite for the next message.

The app manually executes function calls instead of enabling SDK automatic function calling. This makes the agent loop visible and easier to learn.

## Existing database migration

If you already ran the OpenAI version and have a `shop.db`, the updated code adds a `conversation_history` column to `customer_sessions` on startup. It does not delete the product or order tables. The old OpenAI `previous_response_id` column is left in place but is no longer used.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Next milestones

1. Add tests and improve order/address validation.
2. Replace the local SQLite product adapter with the real CMS API.
3. Add FastAPI endpoints for an inbound WhatsApp webhook.
4. Add WhatsApp Cloud API message sending and webhook signature verification.
5. Add idempotency, delivery/fulfillment integration, payment flow, and observability.
