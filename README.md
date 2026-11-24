# ShopBot — WhatsApp AI Sales Assistant (Learning MVP)

A small Python project that demonstrates an LLM agent loop for a retail business.

## What it can do

- List products and current stock from SQLite.
- Search for a product and retrieve its price.
- Prepare an order draft after collecting product quantities and a complete address.
- Confirm a draft only after a clear approval in the customer's latest message.
- Keep a conversation linked to a customer ID using the Responses API response chain.

## Safety and scope

This is a local learning MVP. Confirmation updates a local SQLite order and stock record only. It does **not** accept payment, book a courier, or dispatch a package. Do not connect it to a live shop or real customer data until authentication, webhook verification, idempotency, monitoring, privacy controls, and business-specific order rules are added.

The product names, prices, and stock in `shop/database.py` are demo data only. Replace them with a read-only adapter to the actual CMS before using real catalogue information.

## Requirements

- Python 3.10 or later
- An OpenAI API key with access to a tool-calling model

## Setup (macOS/Linux)

```bash
cd whatsapp_shop_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and set `OPENAI_API_KEY`. Set `OPENAI_MODEL` to a tool-calling model available to your API account if the example model name is not enabled for you.

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
    ├── config.py        # Environment settings
    ├── database.py      # SQLite schema, sample catalogue, session storage
    ├── tools.py         # Business tools the model can call
    └── agent.py         # OpenAI Responses API + agent loop
```

## How the agent loop works

1. `ShopAgent` sends the user's message, instructions, and tool schemas to the model.
2. The model either returns a final text answer or requests one or more function calls.
3. `ShopTools.dispatch()` routes each call to a Python function.
4. The application returns each tool result to the model with its `call_id`.
5. The model can call another tool or produce a final response. The loop has a maximum iteration limit.

## Next milestones

1. Add tests and improve order/address validation.
2. Replace the local SQLite product adapter with the real CMS API.
3. Add FastAPI endpoints for an inbound WhatsApp webhook.
4. Add WhatsApp Cloud API message sending and webhook signature verification.
5. Add idempotency, delivery/fulfillment integration, payment flow, and observability.
