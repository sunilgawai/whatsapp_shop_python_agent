import tempfile
import unittest
from pathlib import Path

from shop.config import Settings
from shop.database import Database
from shop.tools import ShopTools


class ShopToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            openai_api_key="test-key",
            openai_model="test-model",
            max_agent_iterations=3,
            database_path=str(Path(self.temp_dir.name) / "test.db"),
        )
        self.database = Database(settings)
        self.database.initialize()
        self.customer_id = "customer-test-1"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_products_returns_seed_catalogue(self):
        result = ShopTools(self.database, self.customer_id, "show products").list_products()
        names = {product["name"] for product in result["products"]}
        self.assertIn("AirPods Pro", names)

    def test_prepare_order_creates_draft_without_decrementing_stock(self):
        tools = ShopTools(self.database, self.customer_id, "prepare order")
        result = tools.prepare_order(
            items=[{"product_name": "AirPods Pro", "quantity": 2}],
            address_line="Flat 12, Sunshine Apartments",
            locality="Baner",
            city="Pune",
            pincode="411045",
        )
        self.assertTrue(result["created"])
        self.assertEqual(result["status"], "DRAFT")
        self.assertEqual(result["total_rupees"], 49800)

        details = tools.get_product_details("AirPods Pro")
        self.assertEqual(details["stock"], 15)

    def test_confirmation_requires_clear_approval(self):
        create_tools = ShopTools(self.database, self.customer_id, "prepare order")
        draft = create_tools.prepare_order(
            items=[{"product_name": "USB-C Charger", "quantity": 1}],
            address_line="Flat 12, Sunshine Apartments",
            locality="Baner",
            city="Pune",
            pincode="411045",
        )

        non_approval_tools = ShopTools(
            self.database, self.customer_id, "Yes, but change the quantity first."
        )
        result = non_approval_tools.confirm_order(draft["order_id"])
        self.assertFalse(result["confirmed"])

    def test_clear_confirmation_reduces_local_demo_stock(self):
        create_tools = ShopTools(self.database, self.customer_id, "prepare order")
        draft = create_tools.prepare_order(
            items=[{"product_name": "Wireless Mouse", "quantity": 2}],
            address_line="Flat 12, Sunshine Apartments",
            locality="Baner",
            city="Pune",
            pincode="411045",
        )

        confirm_tools = ShopTools(
            self.database, self.customer_id, "Yes, confirm this order."
        )
        result = confirm_tools.confirm_order(draft["order_id"])
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["status"], "CONFIRMED")

        details = confirm_tools.get_product_details("Wireless Mouse")
        self.assertEqual(details["stock"], 20)


if __name__ == "__main__":
    unittest.main()
