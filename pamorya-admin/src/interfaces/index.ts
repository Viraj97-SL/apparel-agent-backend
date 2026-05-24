export interface InventoryRow {
  id: number;
  size: string;
  stock_quantity: number;
}

export interface Product {
  id: number;
  product_name: string;
  category: string;
  price: number;
  description: string;
  image_url: string | null;
  colour: string;
  total_stock: number;
  inventory: InventoryRow[];
}

export interface OrderItem {
  product_name: string;
  size: string;
  quantity: number;
  price: number;
}

export interface Order {
  id: string;
  order_number: string | null;
  status: string;
  total_amount: number;
  created_at: string | null;
  customer_name: string;
  customer_email: string | null;
  customer_phone: string | null;
  shipping_address: string | null;
  items_count: number;
  items: OrderItem[];
}

export interface Customer {
  id: string;
  full_name: string;
  email: string;
  phone_number: string;
  shipping_address: string;
  created_at: string | null;
  order_count: number;
  total_spent: number;
}

export interface DashboardStats {
  total_revenue: number;
  orders_today: number;
  total_orders: number;
  low_stock_count: number;
  out_of_stock_count: number;
  total_customers: number;
  orders_by_status: Record<string, number>;
  revenue_last_7_days: Array<{ date: string; revenue: number }>;
  top_products: Array<{ name: string; quantity: number }>;
}

export const CATEGORIES = [
  "Dresses",
  "Skirts",
  "Tops & Blouses",
  "Pants & Trousers",
  "Jumpers & Knits",
  "Jackets & Outerwear",
  "Sets & Co-ords",
  "General",
];

export const ORDER_STATUSES = ["Draft", "Pending", "Paid", "Shipped", "Cancelled"];
