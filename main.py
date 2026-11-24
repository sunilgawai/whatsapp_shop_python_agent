from shop.agent import ShopAgent
from shop.config import get_settings
from shop.database import Database


def main() -> None:
    settings = get_settings()
    database = Database(settings)
    database.initialize()
    agent = ShopAgent(settings, database)

    # A fixed demo customer ID keeps the same conversation context between messages.
    # A WhatsApp webhook will use the sender's verified WhatsApp number here.
    customer_id = "demo-customer-001"

    print("ShopBot demo is ready.")
    print("Try: 'What products are available?' or 'What is the price of AirPods Pro?'")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if message.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not message:
            continue

        try:
            answer = agent.handle_message(customer_id, message)
            print(f"ShopBot: {answer}\n")
        except Exception as error:
            print(f"ShopBot encountered an error: {error}\n")


if __name__ == "__main__":
    main()
