from langchain_core.tools import tool
from app.database import SessionLocal
from app.models import Product, Order, OrderItem, Customer
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
            time.sleep(1)  # Wait 1 second and try again
            continue
        except Exception as e:
            print(f"❌ DB Error: {e}")
            raise e
    raise Exception("Database is too busy. Please try again.")


@tool
def create_draft_order(product_name: str, size: str, quantity: int, thread_id: str = "guest_user"):
    """Adds an item to the draft order."""
    print(f"DEBUG: Creating draft order for {product_name}, Size: {size}, User: {thread_id}")

    def transaction():
        session = SessionLocal()
        try:
            # 1. Find Product
            product = session.query(Product).filter(Product.product_name.ilike(f"%{product_name}%")).first()
            if not product:
                return f"Error: Product '{product_name}' not found."

            price = float(product.price)
            total = price * int(quantity)

            # 2. Ensure Guest Customer Exists
            customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
            if not customer:
                customer = Customer(customer_id=thread_id, full_name="Guest")
                session.add(customer)
                session.flush()

            # 3. Get/Create Order
            order = session.query(Order).filter(Order.customer_id == thread_id,
                                                Order.status == "pending_payment").first()
            if not order:
                order = Order(customer_id=thread_id, thread_id=thread_id, status="pending_payment", total_amount=0.0)
                session.add(order)
                session.flush()

            # 4. Add Item
            item = OrderItem(order_id=order.order_id, product_name=product.product_name, size=size, quantity=quantity,
                             price_at_purchase=price)
            session.add(item)

            # 5. Update Total
            order.total_amount += total
            session.commit()

            return f"SUCCESS: Added {quantity}x {product.product_name} ({size}). Total: {order.total_amount}. Ask for details."

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
    """Updates customer details and confirms order."""
    print(f"DEBUG: Confirming order for {customer_name}, User: {thread_id}")

    # 🛡️ Guard: Force inputs to string
    customer_name = str(customer_name)
    address = str(address)
    phone = str(phone)

    def transaction():
        session = SessionLocal()
        try:
            # 1. Find Customer
            customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()

            # Auto-fix: Create customer if missing
            if not customer:
                customer = Customer(customer_id=thread_id, full_name=customer_name)
                session.add(customer)
                session.flush()

            # 2. Update Details
            customer.full_name = customer_name
            customer.shipping_address = address
            customer.phone_number = phone

            # 3. Confirm Order
            order = session.query(Order).filter(Order.customer_id == thread_id,
                                                Order.status == "pending_payment").first()
            if order:
                order.status = "confirmed"
                session.commit()
                return "COD_SUCCESS"
            else:
                return "Error: No pending order found to confirm. Did you add items?"

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    try:
        return execute_with_retry(transaction)
    except Exception as e:
        return f"Error confirming: {str(e)}"