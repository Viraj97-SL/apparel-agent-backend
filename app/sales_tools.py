from langchain_core.tools import tool
from app.database import SessionLocal
from app.models import Product, Order, OrderItem, Customer


@tool
def create_draft_order(product_name: str, size: str, quantity: int, thread_id: str = "guest_user"):
    """Adds an item to the draft order."""
    print(f"DEBUG: Creating draft order for {product_name}, Size: {size}, User: {thread_id}")
    session = SessionLocal()
    try:
        # 1. Find Product
        product = session.query(Product).filter(Product.product_name.ilike(f"%{product_name}%")).first()
        if not product:
            print(f"DEBUG: Product {product_name} not found")
            return f"Error: Product '{product_name}' not found."

        price = float(product.price)
        total = price * int(quantity)

        # 2. Ensure Guest Customer Exists
        customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
        if not customer:
            print("DEBUG: Creating new Guest Customer")
            customer = Customer(customer_id=thread_id, full_name="Guest")
            session.add(customer)
            session.flush()

        # 3. Get/Create Order
        order = session.query(Order).filter(Order.customer_id == thread_id, Order.status == "pending_payment").first()
        if not order:
            print("DEBUG: Creating new Order")
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
        print("DEBUG: Order Saved Successfully")

        return f"SUCCESS: Added {quantity}x {product.product_name} ({size}). Total: {order.total_amount}. Ask for details."

    except Exception as e:
        session.rollback()
        print(f"DEBUG ERROR: {e}")
        return f"System Error: {e}"
    finally:
        session.close()


@tool
def confirm_order_details(customer_name: str, address: str, phone: str, thread_id: str = "guest_user"):
    """Updates customer details and confirms order."""
    print(f"DEBUG: Confirming order for {customer_name}, User: {thread_id}")
    session = SessionLocal()
    try:
        # 1. Find Customer
        customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
        if not customer:
            return "Error: No order found. Please add items first."

        # 2. Update Details
        customer.full_name = customer_name
        customer.shipping_address = address
        customer.phone_number = phone

        # 3. Confirm Order
        order = session.query(Order).filter(Order.customer_id == thread_id, Order.status == "pending_payment").first()
        if order:
            order.status = "confirmed"
            session.commit()
            print("DEBUG: Order Confirmed Successfully")
            return "COD_SUCCESS"
        else:
            return "Error: No pending order found to confirm."

    except Exception as e:
        session.rollback()
        print(f"DEBUG ERROR: {e}")
        return f"Error confirming: {e}"
    finally:
        session.close()