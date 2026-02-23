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
