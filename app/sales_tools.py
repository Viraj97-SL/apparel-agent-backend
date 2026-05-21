import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from langchain_core.tools import tool
from sqlalchemy.exc import OperationalError
import time

from app.database import SessionLocal
from app.models import Product, Order, OrderItem, Customer, Inventory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def execute_with_retry(func, max_retries: int = 3):
    """Retry database operations on transient lock/timeout errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except OperationalError:
            logger.warning("DB busy (attempt %d/%d) — retrying...", attempt + 1, max_retries)
            time.sleep(1)
        except Exception as e:
            logger.error("DB error: %s", e)
            raise
    raise Exception("Database is too busy. Please try again.")


def _generate_order_number() -> str:
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"PAM-{date_part}-{suffix}"


def _next_delivery_date(business_days: int = 4) -> str:
    """Return a date string N business days from today (Mon–Fri)."""
    current = date.today()
    added = 0
    while added < business_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current.strftime("%B %d, %Y")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def create_draft_order(product_name: str, size: str, quantity: int, thread_id: str = "guest_user"):
    """Adds an item to the draft order. Returns OUT_OF_STOCK if size unavailable."""
    logger.info("create_draft_order: product=%s size=%s qty=%d thread=%s",
                product_name, size, quantity, thread_id)

    def transaction():
        session = SessionLocal()
        try:
            product = session.query(Product).filter(
                Product.product_name.ilike(f"%{product_name}%")
            ).first()
            if not product:
                return f"Error: Product '{product_name}' not found in our catalogue."

            size_upper = size.strip().upper()
            inv = session.query(Inventory).filter(
                Inventory.product_id == product.product_id,
                Inventory.size == size_upper,
            ).first()

            if inv is not None and inv.stock_quantity == 0:
                available = session.query(Inventory).filter(
                    Inventory.product_id == product.product_id,
                    Inventory.stock_quantity > 0,
                ).all()
                sizes_list = ", ".join(i.size for i in available) if available else "none currently"
                return (
                    f"OUT_OF_STOCK: Size {size_upper} is unavailable for "
                    f"{product.product_name}. Available sizes: {sizes_list}"
                )

            price = float(product.price)
            total_line = price * int(quantity)

            customer = session.query(Customer).filter(
                Customer.customer_id == thread_id
            ).first()
            if not customer:
                customer = Customer(customer_id=thread_id, full_name="Guest")
                session.add(customer)
                session.flush()

            order = session.query(Order).filter(
                Order.customer_id == thread_id,
                Order.status == "pending_payment",
            ).first()
            if not order:
                order = Order(
                    customer_id=thread_id,
                    thread_id=thread_id,
                    status="pending_payment",
                    total_amount=0.0,
                )
                session.add(order)
                session.flush()

            item = OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                product_name=product.product_name,
                size=size_upper,
                quantity=quantity,
                price_at_purchase=price,
            )
            session.add(item)
            order.total_amount += total_line
            session.commit()

            delivery_estimate = _next_delivery_date(4)
            return (
                f"SUCCESS: Added {quantity}x {product.product_name} ({size_upper}) to your order. "
                f"Cart total: LKR {order.total_amount:,.0f}. "
                f"Estimated delivery: {delivery_estimate}. "
                "Please provide your Full Name, Shipping Address, and Phone Number to confirm."
            )

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    try:
        return execute_with_retry(transaction)
    except Exception as e:
        return f"System Error: {str(e)}"


@tool
def view_cart(thread_id: str = "guest_user"):
    """Returns a formatted summary of all items in the current pending cart."""
    logger.info("view_cart: thread=%s", thread_id)

    def transaction():
        session = SessionLocal()
        try:
            order = session.query(Order).filter(
                Order.customer_id == thread_id,
                Order.status == "pending_payment",
            ).first()

            if not order or not order.items:
                return "Your cart is empty. Browse our collection and add items to get started!"

            lines = ["CART:"]
            for i, item in enumerate(order.items, 1):
                line_total = item.price_at_purchase * item.quantity
                lines.append(
                    f"  {i}. {item.quantity}x {item.product_name} ({item.size})"
                    f" — LKR {line_total:,.0f}"
                )
            lines.append("  " + "─" * 35)
            lines.append(f"  Total: LKR {order.total_amount:,.0f}")
            lines.append(f"  Estimated delivery: {_next_delivery_date(4)}")
            return "\n".join(lines)

        finally:
            session.close()

    try:
        return execute_with_retry(transaction)
    except Exception as e:
        return f"System Error: {str(e)}"


@tool
def remove_from_cart(product_name: str, thread_id: str = "guest_user"):
    """Removes an item from the cart by product name and returns the updated cart."""
    logger.info("remove_from_cart: product=%s thread=%s", product_name, thread_id)

    def transaction():
        session = SessionLocal()
        try:
            order = session.query(Order).filter(
                Order.customer_id == thread_id,
                Order.status == "pending_payment",
            ).first()

            if not order:
                return "No active cart found."

            item = session.query(OrderItem).filter(
                OrderItem.order_id == order.order_id,
                OrderItem.product_name.ilike(f"%{product_name}%"),
            ).first()

            if not item:
                return f"'{product_name}' was not found in your cart."

            removed_total = item.price_at_purchase * item.quantity
            session.delete(item)
            order.total_amount = max(0.0, order.total_amount - removed_total)
            session.commit()
            session.refresh(order)

            if not order.items:
                return f"Removed {product_name}. Your cart is now empty."

            lines = [f"Removed {product_name}. Updated cart:", "CART:"]
            for i, it in enumerate(order.items, 1):
                line_total = it.price_at_purchase * it.quantity
                lines.append(
                    f"  {i}. {it.quantity}x {it.product_name} ({it.size})"
                    f" — LKR {line_total:,.0f}"
                )
            lines.append("  " + "─" * 35)
            lines.append(f"  Total: LKR {order.total_amount:,.0f}")
            return "\n".join(lines)

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    try:
        return execute_with_retry(transaction)
    except Exception as e:
        return f"System Error: {str(e)}"


@tool
def confirm_order_details(
    customer_name: str,
    address: str,
    phone: str,
    thread_id: str = "guest_user",
):
    """
    Updates customer details, confirms the COD order, and returns a receipt JSON.
    Call this only when you have all three: customer_name, address, and phone.
    """
    logger.info("confirm_order_details: customer=%s thread=%s", customer_name, thread_id)

    customer_name = str(customer_name)
    address = str(address)
    phone = str(phone)

    def transaction():
        session = SessionLocal()
        try:
            customer = session.query(Customer).filter(
                Customer.customer_id == thread_id
            ).first()
            if not customer:
                customer = Customer(customer_id=thread_id, full_name=customer_name)
                session.add(customer)
                session.flush()

            customer.full_name = customer_name
            customer.shipping_address = address
            customer.phone_number = phone

            order = session.query(Order).filter(
                Order.customer_id == thread_id,
                Order.status == "pending_payment",
            ).first()
            if not order:
                return "Error: No pending order found. Did you add items first?"

            order_number = _generate_order_number()
            order.order_number = order_number
            order.status = "confirmed"

            delivery_date = _next_delivery_date(4)

            items_payload = [
                {
                    "name": item.product_name,
                    "size": item.size,
                    "qty": item.quantity,
                    "price": int(item.price_at_purchase),
                }
                for item in order.items
            ]

            receipt = {
                "status": "COD_SUCCESS",
                "order_number": order_number,
                "customer_name": customer_name,
                "items": items_payload,
                "total": int(order.total_amount),
                "address": address,
                "phone": phone,
                "delivery_date": delivery_date,
                "payment_method": "Cash on Delivery",
                "message": (
                    f"Your order {order_number} is confirmed! "
                    f"We'll WhatsApp you at {phone} once your order is dispatched. "
                    f"Expected delivery: {delivery_date}."
                ),
                "whatsapp_note": (
                    f"Hi {customer_name}! Your Pamorya order {order_number} "
                    f"(LKR {int(order.total_amount):,}) is confirmed. "
                    f"Expected delivery: {delivery_date}. COD payment at the door."
                ),
            }

            session.commit()
            return json.dumps(receipt)

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    try:
        return execute_with_retry(transaction)
    except Exception as e:
        return f"Error confirming order: {str(e)}"


@tool
def get_order_status(order_number: str = "", thread_id: str = "guest_user"):
    """
    Look up the status of an existing order by order number (PAM-YYYYMMDD-XXXX)
    or by thread_id (returns the most recent order for this conversation).
    """
    logger.info("get_order_status: order_number=%s thread=%s", order_number, thread_id)

    def transaction():
        session = SessionLocal()
        try:
            if order_number:
                order = session.query(Order).filter(
                    Order.order_number == order_number.strip().upper()
                ).first()
            else:
                order = session.query(Order).filter(
                    Order.thread_id == thread_id
                ).order_by(Order.created_at.desc()).first()

            if not order:
                return "No order found. If you placed an order recently, please share your order number (e.g. PAM-20260521-AB12)."

            items_summary = ", ".join(
                f"{it.quantity}x {it.product_name} ({it.size})" for it in order.items
            )
            delivery = _next_delivery_date(4) if order.status == "confirmed" else "TBD"

            STATUS_LABELS = {
                "pending_payment": "Pending",
                "confirmed": "Confirmed — preparing for dispatch",
                "shipped": "Shipped — on its way!",
                "delivered": "Delivered",
                "cancelled": "Cancelled",
            }
            status_label = STATUS_LABELS.get(order.status, order.status)

            return (
                f"Order {order.order_number or '(pending)'}:\n"
                f"  Status: {status_label}\n"
                f"  Items: {items_summary or 'none'}\n"
                f"  Total: LKR {int(order.total_amount):,}\n"
                f"  Expected delivery: {delivery}"
            )

        finally:
            session.close()

    try:
        return execute_with_retry(transaction)
    except Exception as e:
        return f"System Error: {str(e)}"
