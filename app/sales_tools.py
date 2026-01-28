from langchain_core.tools import tool
from app.database import SessionLocal
from app.models import Product, Order, OrderItem, Customer

@tool
def create_draft_order(product_name: str, size: str, quantity: int, thread_id: str = "guest_user"):
    """
    Adds an item to the user's draft order.
    """
    session = SessionLocal()
    try:
        # 1. Find Product
        product = session.query(Product).filter(Product.product_name.ilike(f"%{product_name}%")).first()
        if not product:
            return f"Error: Product '{product_name}' not found."

        price = float(product.price)
        total_item_price = price * int(quantity)

        # 2. Ensure Customer (Guest) exists
        customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
        if not customer:
            customer = Customer(customer_id=thread_id, full_name="Guest")
            session.add(customer)
            session.flush()

        # 3. Find or Create Draft Order
        order = session.query(Order).filter(
            Order.customer_id == thread_id,
            Order.status == "pending_payment"
        ).first()

        if not order:
            order = Order(
                customer_id=thread_id,
                thread_id=thread_id,  # ✅ Populate the new column
                status="pending_payment",
                total_amount=0.0
            )
            session.add(order)
            session.flush()

        # 4. Add Item
        new_item = OrderItem(
            order_id=order.order_id,
            product_name=product.product_name,
            size=size,
            quantity=quantity,
            price_at_purchase=price
        )
        session.add(new_item)

        # 5. Update Total
        order.total_amount += total_item_price
        session.commit()

        return (
            f"SUCCESS: Added {quantity}x {product.product_name} ({size}) to order. "
            f"Order Total: LKR {order.total_amount}. "
            f"Ask for Name, Address, and Phone to confirm."
        )

    except Exception as e:
        session.rollback()
        return f"System Error: {e}"
    finally:
        session.close()

@tool
def confirm_order_details(customer_name: str, address: str, phone: str, thread_id: str = "guest_user"):
    """
    Updates the Guest Customer with real details and confirms the order.
    """
    session = SessionLocal()
    try:
        # 1. Find Customer
        customer = session.query(Customer).filter(Customer.customer_id == thread_id).first()
        if not customer:
            return "Error: No customer record found. Create an order first."

        # 2. Update Details
        customer.full_name = customer_name
        customer.shipping_address = address
        customer.phone_number = phone

        # 3. Confirm Order
        order = session.query(Order).filter(
            Order.customer_id == thread_id,
            Order.status == "pending_payment"
        ).first()

        if order:
            order.status = "confirmed"

        session.commit()
        return "COD_SUCCESS"

    except Exception as e:
        return f"Error confirming: {e}"
    finally:
        session.close()