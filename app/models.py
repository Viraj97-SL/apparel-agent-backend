from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum, Boolean, Text
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


# --- PRODUCT MANAGEMENT ---
class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String, index=True)
    category = Column(String)
    price = Column(Float)
    description = Column(Text)
    image_url = Column(String)
    colour = Column(String)

    # Relationships
    inventory = relationship("Inventory", back_populates="product")


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.product_id"))
    size = Column(String)
    stock_quantity = Column(Integer, default=0)

    product = relationship("Product", back_populates="inventory")


# --- CUSTOMER DATA ---
class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    shipping_address = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    orders = relationship("Order", back_populates="customer")


# --- ORDER MANAGEMENT ---
class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))  # e.g. "ORD-123..."
    customer_id = Column(String, ForeignKey("customers.customer_id"))
    status = Column(String, default="pending_payment")  # pending, paid, shipped, delivered, returned
    total_amount = Column(Float, default=0.0)
    stripe_payment_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("orders.order_id"))
    product_name = Column(String)  # Snapshot of name at time of purchase
    size = Column(String)
    quantity = Column(Integer)
    price_at_purchase = Column(Float)

    order = relationship("Order", back_populates="items")


# --- UTILS ---
class Return(Base):
    __tablename__ = "returns"

    return_id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.order_id"))
    product_ids = Column(String)  # JSON string of product IDs being returned
    status = Column(String)
    return_date = Column(DateTime(timezone=True), server_default=func.now())


class RestockNotification(Base):
    __tablename__ = "restock_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_email = Column(String)
    product_id = Column(Integer)
    size = Column(String)
    status = Column(String, default="Pending")