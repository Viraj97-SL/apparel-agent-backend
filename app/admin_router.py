import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Customer,
    Inventory,
    Order,
    OrderItem,
    Product,
    RestockNotification,
)

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "pamorya-admin-2025")

VALID_STATUSES = {"Draft", "Pending", "Paid", "Shipped", "Cancelled"}


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_admin(x_admin_key: str = Header(..., alias="x-admin-key")):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ProductCreate(BaseModel):
    product_name: str
    category: str
    price: float
    description: str
    image_url: Optional[str] = None
    colour: str


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    colour: Optional[str] = None


class InventoryCreate(BaseModel):
    product_id: int
    size: str
    stock_quantity: int = 0


class InventoryUpdate(BaseModel):
    size: Optional[str] = None
    stock_quantity: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def dashboard_stats(
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    today = datetime.now(timezone.utc).date()

    total_revenue = db.query(func.sum(Order.total_amount)).filter(
        Order.status.in_(["Paid", "Shipped"])
    ).scalar() or 0.0

    orders_today = db.query(func.count(Order.order_id)).filter(
        func.date(Order.created_at) == today
    ).scalar() or 0

    total_orders = db.query(func.count(Order.order_id)).scalar() or 0

    low_stock = db.query(func.count(Inventory.inventory_id)).filter(
        Inventory.stock_quantity <= 3,
        Inventory.stock_quantity > 0,
    ).scalar() or 0

    out_of_stock = db.query(func.count(Inventory.inventory_id)).filter(
        Inventory.stock_quantity == 0
    ).scalar() or 0

    total_customers = db.query(func.count(Customer.customer_id)).scalar() or 0

    status_rows = db.query(Order.status, func.count(Order.order_id)).group_by(Order.status).all()
    orders_by_status = {s: c for s, c in status_rows}

    revenue_last_7: list[dict] = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        rev = db.query(func.sum(Order.total_amount)).filter(
            func.date(Order.created_at) == day,
            Order.status.in_(["Paid", "Shipped"]),
        ).scalar() or 0.0
        revenue_last_7.append({"date": str(day), "revenue": float(rev)})

    top_products = (
        db.query(OrderItem.product_name, func.sum(OrderItem.quantity).label("qty"))
        .group_by(OrderItem.product_name)
        .order_by(desc("qty"))
        .limit(5)
        .all()
    )

    return {
        "total_revenue": float(total_revenue),
        "orders_today": orders_today,
        "total_orders": total_orders,
        "low_stock_count": low_stock,
        "out_of_stock_count": out_of_stock,
        "total_customers": total_customers,
        "orders_by_status": orders_by_status,
        "revenue_last_7_days": revenue_last_7,
        "top_products": [{"name": p[0], "quantity": int(p[1])} for p in top_products],
    }


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def _product_payload(p: Product, db: Session) -> dict:
    inventory = db.query(Inventory).filter(Inventory.product_id == p.product_id).all()
    return {
        "id": p.product_id,
        "product_name": p.product_name,
        "category": p.category,
        "price": p.price,
        "description": p.description,
        "image_url": p.image_url,
        "colour": p.colour,
        "total_stock": sum(i.stock_quantity for i in inventory),
        "inventory": [
            {"id": i.inventory_id, "size": i.size, "stock_quantity": i.stock_quantity}
            for i in inventory
        ],
    }


@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    query = db.query(Product)
    if search:
        query = query.filter(Product.product_name.ilike(f"%{search}%"))
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))

    total = query.count()
    products = (
        query.order_by(Product.product_name)
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    return {"data": [_product_payload(p, db) for p in products], "total": total}


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_payload(product, db)


@router.post("/products", status_code=201)
def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    product = Product(**body.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return _product_payload(product, db)


@router.patch("/products/{product_id}")
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return _product_payload(product, db)


@router.delete("/products/{product_id}")
def archive_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """Soft delete: zeroes all stock to preserve order history FK integrity."""
    inventories = db.query(Inventory).filter(Inventory.product_id == product_id).all()
    for inv in inventories:
        inv.stock_quantity = 0
    db.commit()
    return {"success": True, "message": "Product archived — all stock set to 0."}


# ---------------------------------------------------------------------------
# Inventory rows
# ---------------------------------------------------------------------------

@router.post("/inventory", status_code=201)
def create_inventory_row(
    body: InventoryCreate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    inv = Inventory(
        product_id=body.product_id,
        size=body.size.strip().upper(),
        stock_quantity=body.stock_quantity,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return {"id": inv.inventory_id, "size": inv.size, "stock_quantity": inv.stock_quantity}


@router.patch("/inventory/{inventory_id}")
def update_inventory_row(
    inventory_id: int,
    body: InventoryUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    inv = db.query(Inventory).filter(Inventory.inventory_id == inventory_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory row not found")
    if body.size is not None:
        inv.size = body.size.strip().upper()
    if body.stock_quantity is not None:
        inv.stock_quantity = body.stock_quantity
    db.commit()
    return {"id": inv.inventory_id, "size": inv.size, "stock_quantity": inv.stock_quantity}


@router.delete("/inventory/{inventory_id}")
def delete_inventory_row(
    inventory_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    inv = db.query(Inventory).filter(Inventory.inventory_id == inventory_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory row not found")
    db.delete(inv)
    db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def _order_payload(o: Order, db: Session) -> dict:
    customer = (
        db.query(Customer).filter(Customer.customer_id == o.customer_id).first()
        if o.customer_id
        else None
    )
    items = db.query(OrderItem).filter(OrderItem.order_id == o.order_id).all()
    return {
        "id": o.order_id,
        "order_number": o.order_number,
        "status": o.status,
        "total_amount": o.total_amount,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "customer_name": customer.full_name if customer else "Guest",
        "customer_email": customer.email if customer else None,
        "customer_phone": customer.phone_number if customer else None,
        "shipping_address": customer.shipping_address if customer else None,
        "items_count": len(items),
        "items": [
            {
                "product_name": i.product_name,
                "size": i.size,
                "quantity": i.quantity,
                "price": i.price_at_purchase,
            }
            for i in items
        ],
    }


@router.get("/orders")
def list_orders(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    query = db.query(Order)
    if status and status != "All":
        query = query.filter(Order.status == status)

    total = query.count()
    orders = (
        query.order_by(desc(Order.created_at))
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    return {"data": [_order_payload(o, db) for o in orders], "total": total}


@router.patch("/orders/{order_id}")
def update_order_status(
    order_id: str,
    body: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
        )
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = body.status
    db.commit()
    return {"id": order_id, "status": body.status}


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@router.get("/customers")
def list_customers(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    total = db.query(func.count(Customer.customer_id)).scalar() or 0
    customers = (
        db.query(Customer)
        .order_by(desc(Customer.created_at))
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )

    result = []
    for c in customers:
        order_count = (
            db.query(func.count(Order.order_id))
            .filter(Order.customer_id == c.customer_id)
            .scalar() or 0
        )
        total_spent = (
            db.query(func.sum(Order.total_amount))
            .filter(
                Order.customer_id == c.customer_id,
                Order.status.in_(["Paid", "Shipped"]),
            )
            .scalar() or 0.0
        )
        result.append({
            "id": c.customer_id,
            "full_name": c.full_name or "—",
            "email": c.email or "—",
            "phone_number": c.phone_number or "—",
            "shipping_address": c.shipping_address or "—",
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "order_count": order_count,
            "total_spent": float(total_spent),
        })

    return {"data": result, "total": total}


# ---------------------------------------------------------------------------
# Restock notifications
# ---------------------------------------------------------------------------

@router.get("/restock")
def list_restock_notifications(
    db: Session = Depends(get_db),
    _: None = Depends(verify_admin),
):
    notifications = (
        db.query(RestockNotification)
        .filter(RestockNotification.status == "Pending")
        .all()
    )
    result = []
    for n in notifications:
        product = db.query(Product).filter(Product.product_id == n.product_id).first()
        result.append({
            "id": n.id,
            "customer_email": n.customer_email,
            "product_name": product.product_name if product else "Unknown",
            "size": n.size,
            "status": n.status,
        })
    return {"data": result, "total": len(result)}


# ---------------------------------------------------------------------------
# On-demand Excel import (replaces startup sync)
# ---------------------------------------------------------------------------

@router.post("/import-excel")
def import_excel(_: None = Depends(verify_admin)):
    """Trigger a manual Excel import. Use when bulk-loading from the spreadsheet."""
    try:
        from app.db_builder import populate_initial_data
        populate_initial_data()
        return {"success": True, "message": "Excel import completed."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
