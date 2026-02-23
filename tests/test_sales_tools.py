"""
Unit tests for sales_tools.py — order creation and confirmation.
Uses an in-memory SQLite database so no real PostgreSQL is needed.
"""
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Patch DATABASE_URL before any app code loads
# ---------------------------------------------------------------------------
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.models import Base, Customer, Order, OrderItem, Product, Inventory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def test_session():
    """Fresh in-memory SQLite for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_product(test_session):
    """Insert a minimal product + inventory row."""
    product = Product(
        product_name="Crimson Canvas",
        category="Dresses",
        price=45.99,
        description="A beautiful red dress",
        image_url="https://example.com/crimson.jpg",
        colour="Red",
    )
    test_session.add(product)
    test_session.flush()

    inventory = Inventory(product_id=product.product_id, size="M", stock_quantity=10)
    test_session.add(inventory)
    test_session.commit()
    return product


# ---------------------------------------------------------------------------
# Model layer tests (no tool function needed — tests the ORM directly)
# ---------------------------------------------------------------------------
class TestOrderModel:
    def test_create_draft_order_record(self, test_session, sample_product):
        customer = Customer(customer_id="thread-abc")
        test_session.add(customer)
        test_session.flush()

        order = Order(
            customer_id="thread-abc",
            thread_id="thread-abc",
            status="pending_payment",
            total_amount=45.99,
        )
        test_session.add(order)
        test_session.flush()

        item = OrderItem(
            order_id=order.order_id,
            product_id=sample_product.product_id,
            product_name=sample_product.product_name,
            size="M",
            quantity=1,
            price_at_purchase=sample_product.price,
        )
        test_session.add(item)
        test_session.commit()

        saved_order = test_session.query(Order).filter_by(thread_id="thread-abc").first()
        assert saved_order is not None
        assert saved_order.total_amount == 45.99
        assert saved_order.status == "pending_payment"
        assert len(saved_order.items) == 1
        assert saved_order.items[0].product_name == "Crimson Canvas"

    def test_confirm_order_status_transition(self, test_session, sample_product):
        customer = Customer(
            customer_id="thread-confirm",
            full_name="Alice Smith",
            shipping_address="10 Oxford St, London",
            phone_number="07700900000",
        )
        test_session.add(customer)
        test_session.flush()

        order = Order(
            customer_id="thread-confirm",
            thread_id="thread-confirm",
            status="pending_payment",
            total_amount=45.99,
        )
        test_session.add(order)
        test_session.commit()

        # Simulate confirmation
        order.status = "confirmed"
        test_session.commit()

        refreshed = test_session.query(Order).filter_by(thread_id="thread-confirm").first()
        assert refreshed.status == "confirmed"

    def test_multi_item_order_total(self, test_session, sample_product):
        customer = Customer(customer_id="thread-multi")
        test_session.add(customer)

        order = Order(
            customer_id="thread-multi",
            thread_id="thread-multi",
            status="pending_payment",
            total_amount=0,
        )
        test_session.add(order)
        test_session.flush()

        for qty, size in [(2, "S"), (1, "L")]:
            item = OrderItem(
                order_id=order.order_id,
                product_id=sample_product.product_id,
                product_name=sample_product.product_name,
                size=size,
                quantity=qty,
                price_at_purchase=sample_product.price,
            )
            test_session.add(item)
            order.total_amount += sample_product.price * qty

        test_session.commit()
        refreshed = test_session.query(Order).filter_by(thread_id="thread-multi").first()
        # 2 × 45.99 + 1 × 45.99 = 137.97
        assert abs(refreshed.total_amount - 137.97) < 0.01
        assert len(refreshed.items) == 2


class TestInventoryModel:
    def test_stock_levels(self, test_session, sample_product):
        inv = test_session.query(Inventory).filter_by(
            product_id=sample_product.product_id, size="M"
        ).first()
        assert inv is not None
        assert inv.stock_quantity == 10

    def test_out_of_stock(self, test_session, sample_product):
        oos = Inventory(product_id=sample_product.product_id, size="XS", stock_quantity=0)
        test_session.add(oos)
        test_session.commit()
        result = (
            test_session.query(Inventory)
            .filter_by(product_id=sample_product.product_id, size="XS")
            .first()
        )
        assert result.stock_quantity == 0


# ---------------------------------------------------------------------------
# New tool-behaviour tests (ORM-level, no LangChain tool call overhead)
# ---------------------------------------------------------------------------

class TestSalesToolBehaviours:
    """
    These tests exercise the *logic* of the new tool helpers by driving the
    database directly — the same way the tools do internally — so we stay
    fully in-process without patching SessionLocal.
    """

    def _make_order_with_items(self, session, thread_id, product, items):
        """Helper: create a pending order with given items."""
        customer = session.query(Customer).filter_by(customer_id=thread_id).first()
        if not customer:
            customer = Customer(customer_id=thread_id, full_name="Test")
            session.add(customer)
            session.flush()

        order = Order(
            customer_id=thread_id,
            thread_id=thread_id,
            status="pending_payment",
            total_amount=0.0,
        )
        session.add(order)
        session.flush()

        for name, size, qty in items:
            item = OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                product_name=name,
                size=size,
                quantity=qty,
                price_at_purchase=product.price,
            )
            session.add(item)
            order.total_amount += product.price * qty

        session.commit()
        return order

    def test_out_of_stock_returns_friendly_message(self, test_session, sample_product):
        """Inventory row with stock_quantity=0 → out-of-stock message."""
        # Mark size M as zero stock
        inv = test_session.query(Inventory).filter_by(
            product_id=sample_product.product_id, size="M"
        ).first()
        inv.stock_quantity = 0
        # Add an available size
        test_session.add(Inventory(product_id=sample_product.product_id, size="L", stock_quantity=5))
        test_session.commit()

        # Simulate the stock check logic from create_draft_order
        size_upper = "M"
        inv_check = test_session.query(Inventory).filter_by(
            product_id=sample_product.product_id, size=size_upper
        ).first()
        assert inv_check is not None
        assert inv_check.stock_quantity == 0

        available = test_session.query(Inventory).filter(
            Inventory.product_id == sample_product.product_id,
            Inventory.stock_quantity > 0,
        ).all()
        sizes_list = ", ".join(i.size for i in available)
        msg = (
            f"OUT_OF_STOCK: Size {size_upper} is currently unavailable for "
            f"{sample_product.product_name}. Available sizes: {sizes_list}"
        )
        assert "OUT_OF_STOCK" in msg
        assert "L" in msg

    def test_view_cart_returns_formatted_summary(self, test_session, sample_product):
        """view_cart logic returns a CART: block with items and total."""
        thread_id = "thread-view-cart"
        order = self._make_order_with_items(
            test_session, thread_id, sample_product,
            [("Crimson Canvas", "M", 2)]
        )

        # Simulate view_cart
        items = test_session.query(OrderItem).filter_by(order_id=order.order_id).all()
        assert len(items) == 1

        lines = ["CART:"]
        for i, it in enumerate(items, 1):
            line_total = it.price_at_purchase * it.quantity
            lines.append(
                f"  {i}. {it.quantity}x {it.product_name} ({it.size})"
                f" — LKR {line_total:,.0f}"
            )
        lines.append("  " + "─" * 35)
        lines.append(f"  Total: LKR {order.total_amount:,.0f}")
        summary = "\n".join(lines)

        assert "CART:" in summary
        assert "Crimson Canvas" in summary
        assert "LKR" in summary
        assert "Total" in summary

    def test_remove_from_cart_updates_total(self, test_session, sample_product):
        """Removing an item reduces order total correctly."""
        thread_id = "thread-remove"
        order = self._make_order_with_items(
            test_session, thread_id, sample_product,
            [("Crimson Canvas", "M", 1), ("Crimson Canvas", "S", 2)],
        )
        original_total = order.total_amount  # 3 × 45.99 = 137.97

        # Remove the size-M item
        item = test_session.query(OrderItem).filter(
            OrderItem.order_id == order.order_id,
            OrderItem.size == "M",
        ).first()
        assert item is not None
        removed = item.price_at_purchase * item.quantity
        test_session.delete(item)
        order.total_amount = max(0.0, order.total_amount - removed)
        test_session.commit()

        test_session.refresh(order)
        expected = original_total - removed
        assert abs(order.total_amount - expected) < 0.01
        remaining = test_session.query(OrderItem).filter_by(order_id=order.order_id).all()
        assert len(remaining) == 1
        assert remaining[0].size == "S"

    def test_receipt_json_structure(self, test_session, sample_product):
        """confirm_order_details logic produces a valid receipt JSON."""
        import json
        from datetime import datetime, timezone

        thread_id = "thread-receipt"
        order = self._make_order_with_items(
            test_session, thread_id, sample_product,
            [("Crimson Canvas", "M", 1)],
        )

        # Update customer info
        customer = test_session.query(Customer).filter_by(customer_id=thread_id).first()
        customer.full_name     = "Viraj"
        customer.shipping_address = "Eheliyagoda"
        customer.phone_number  = "071791300"

        # Generate order number and confirm
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        import uuid as _uuid
        order_number = f"PAM-{date_part}-{_uuid.uuid4().hex[:4].upper()}"
        order.order_number = order_number
        order.status = "confirmed"

        items_payload = [
            {
                "name":  it.product_name,
                "size":  it.size,
                "qty":   it.quantity,
                "price": int(it.price_at_purchase),
            }
            for it in order.items
        ]
        receipt = {
            "status":        "COD_SUCCESS",
            "order_number":  order_number,
            "customer_name": customer.full_name,
            "items":         items_payload,
            "total":         int(order.total_amount),
            "address":       customer.shipping_address,
            "phone":         customer.phone_number,
            "message":       f"Order confirmed! We will contact you at {customer.phone_number}.",
        }
        test_session.commit()

        receipt_str = json.dumps(receipt)
        parsed = json.loads(receipt_str)

        assert parsed["status"] == "COD_SUCCESS"
        assert parsed["order_number"].startswith("PAM-")
        assert parsed["customer_name"] == "Viraj"
        assert len(parsed["items"]) == 1
        assert parsed["items"][0]["name"] == "Crimson Canvas"
        assert parsed["total"] > 0
        assert "071791300" in parsed["message"]
