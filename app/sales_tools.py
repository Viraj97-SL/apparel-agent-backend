import json
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool
from app.database import SessionLocal
from app.models import Product, Order, OrderItem, Customer, Inventory
from sqlalchemy.exc import OperationalError
import time


# --- Helper: Retry Logic ---
def execute_with_retry(func, max_retries=3):
    """Retries database operations if they hit a lock or timeout."""
    for attempt in range(max_retries):
        try:
            return func()
        except OperationalError as e:
            print(f"⚠️ DB Busy/Locked (Attempt {attempt + 1}/{max_retries}). Retrying...")
            time.sleep(1)
            continue
        except Exception as e:
            print(f"❌ DB Error: {e}")
            raise e
    raise Exception("Database is too busy. Please try again.")


def _generate_order_number() -> str:
    """Generates a human-readable order number: PAM-YYYYMMDD-XXXX"""
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"PAM-{date_part}-{suffix}"


@tool
def create_draft_order(product_name: str, size: str, quantity: int, thread_id: str = "guest_user"):
    """Adds an item to the draft order. Returns OUT_OF_STOCK if size unavailable."""
    print(f"DEBUG: Creating draft order for {product_name}, Size: {size}, User: {thread_id}")

    def transaction():
        session = SessionLocal()
        try:
            # 1. Find Product
            product = session.query(Product).filter(Product.product_name.ilike(f"%{product_name}%")).first()
            if not product:
                return f"Error: Product '{product_name}' not found."

            # 2. Stock check
            size_upper = size.strip().upper()
            inv = session.query(Inventory).filter(
                Inventory.product_id == product.product_id,
                Inventory.size == size_upper,
            ).first()

            if inv is not None and inv.stock_quantity == 0:
                # List available sizes
                available = session.query(Inventory).filter(
                    Inventory.product_id == product.product_id,
                    Inventory.stock_quantity > 0,
                ).all()
                sizes_list = ", ".join(i.size for i in available) if available else "none currently"
                return (
                    f"OUT_OF_STOCK: Size {size_upper} is currently unavailable for "
                    f"{product.product_name}. Available sizes: {sizes_list}"
                )

            price = float(product.price)
            total = price * int(quantity)

            # 3. Ensure Guest Customer Exists
            customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
            if not customer:
                customer = Customer(customer_id=thread_id, full_name="Guest")
                session.add(customer)
                session.flush()

            # 4. Get/Create Order
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

            # 5. Add Item
            item = OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                product_name=product.product_name,
                size=size_upper,
                quantity=quantity,
                price_at_purchase=price,
            )
            session.add(item)

            # 6. Update Total
            order.total_amount += total
            session.commit()

            return (
                f"SUCCESS: Added {quantity}x {product.product_name} ({size_upper}). "
                f"Total: LKR {order.total_amount:,.0f}. Ask for details."
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
    print(f"DEBUG: Viewing cart for {thread_id}")

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
    print(f"DEBUG: Removing '{product_name}' from cart for {thread_id}")

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

            # Return updated cart view
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
def confirm_order_details(customer_name: str, address: str, phone: str, thread_id: str = "guest_user"):
    """Updates customer details, confirms the order, and returns a structured receipt JSON."""
    print(f"DEBUG: Confirming order for {customer_name}, User: {thread_id}")

    # Guard: force inputs to string
    customer_name = str(customer_name)
    address = str(address)
    phone = str(phone)

    def transaction():
        session = SessionLocal()
        try:
            # 1. Find/create Customer
            customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
            if not customer:
                customer = Customer(customer_id=thread_id, full_name=customer_name)
                session.add(customer)
                session.flush()

            # 2. Update Details
            customer.full_name = customer_name
            customer.shipping_address = address
            customer.phone_number = phone

            # 3. Find Order
            order = session.query(Order).filter(
                Order.customer_id == thread_id,
                Order.status == "pending_payment",
            ).first()
            if not order:
                return "Error: No pending order found to confirm. Did you add items?"

            # 4. Generate order number and confirm
            order_number = _generate_order_number()
            order.order_number = order_number
            order.status = "confirmed"

            # 5. Build receipt payload
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
                "message": (
                    f"Order confirmed! We will contact you at {phone} to arrange delivery."
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
        return f"Error confirming: {str(e)}"
