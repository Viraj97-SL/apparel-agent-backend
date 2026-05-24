import { List, useTable } from "@refinedev/antd";
import { useNotification } from "@refinedev/core";
import {
  Descriptions,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";
import type { Order, OrderItem } from "../../interfaces";
import { ORDER_STATUSES } from "../../interfaces";
import { apiClient } from "../../providers/dataProvider";

const { Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  Paid: "green",
  Shipped: "blue",
  Pending: "orange",
  Draft: "default",
  Cancelled: "red",
};

export const OrderList: React.FC = () => {
  const { open: notify } = useNotification();
  const [statusFilter, setStatusFilter] = useState<string>("All");
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const { tableProps, setFilters } = useTable<Order>({
    resource: "orders",
    pagination: { pageSize: 20 },
    syncWithLocation: true,
  });

  const handleStatusFilter = (value: string) => {
    setStatusFilter(value);
    setFilters([{ field: "status", operator: "eq", value }]);
  };

  const handleStatusUpdate = async (orderId: string, newStatus: string) => {
    setUpdatingId(orderId);
    try {
      await apiClient.patch(`/admin/orders/${orderId}`, { status: newStatus });
      notify?.({ type: "success", message: `Order updated to ${newStatus}`, description: "" });
      // Refresh table
      tableProps.onChange?.({ current: 1 }, {}, {}, { action: "paginate" });
    } catch {
      notify?.({ type: "error", message: "Failed to update order status", description: "" });
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <List
      headerButtons={
        <Select
          value={statusFilter}
          onChange={handleStatusFilter}
          style={{ width: 160 }}
          options={[
            { label: "All Orders", value: "All" },
            ...ORDER_STATUSES.map((s) => ({ label: s, value: s })),
          ]}
        />
      }
    >
      <Table
        {...tableProps}
        rowKey="id"
        expandable={{
          expandedRowRender: (record: Order) => (
            <Descriptions bordered size="small" column={2} style={{ margin: 0 }}>
              <Descriptions.Item label="Customer">
                {record.customer_name}
              </Descriptions.Item>
              <Descriptions.Item label="Email">
                {record.customer_email || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Phone">
                {record.customer_phone || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Address" span={2}>
                {record.shipping_address || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Items" span={2}>
                <Table
                  dataSource={record.items}
                  rowKey={(r: OrderItem) => `${r.product_name}-${r.size}`}
                  pagination={false}
                  size="small"
                  columns={[
                    { title: "Product", dataIndex: "product_name", key: "product_name" },
                    { title: "Size", dataIndex: "size", key: "size" },
                    { title: "Qty", dataIndex: "quantity", key: "quantity" },
                    {
                      title: "Unit Price",
                      dataIndex: "price",
                      key: "price",
                      render: (v: number) => `LKR ${v.toLocaleString()}`,
                    },
                  ]}
                />
              </Descriptions.Item>
            </Descriptions>
          ),
        }}
      >
        <Table.Column
          title="Order #"
          dataIndex="order_number"
          key="order_number"
          render={(v: string | null) => v ?? <Text type="secondary">—</Text>}
        />
        <Table.Column
          title="Date"
          dataIndex="created_at"
          key="created_at"
          render={(v: string | null) =>
            v ? new Date(v).toLocaleDateString("en-GB") : "—"
          }
        />
        <Table.Column title="Customer" dataIndex="customer_name" key="customer_name" />
        <Table.Column
          title="Items"
          dataIndex="items_count"
          key="items_count"
          align="center"
        />
        <Table.Column
          title="Total (LKR)"
          dataIndex="total_amount"
          key="total_amount"
          align="right"
          render={(v: number) => <strong>{v.toLocaleString()}</strong>}
        />
        <Table.Column
          title="Status"
          dataIndex="status"
          key="status"
          render={(status: string, record: Order) => (
            <Select
              value={status}
              style={{ width: 130 }}
              loading={updatingId === record.id}
              onChange={(newStatus) => handleStatusUpdate(record.id, newStatus)}
              options={ORDER_STATUSES.map((s) => ({
                label: (
                  <Tag color={STATUS_COLOR[s]} style={{ margin: 0 }}>
                    {s}
                  </Tag>
                ),
                value: s,
              }))}
            />
          )}
        />
      </Table>
    </List>
  );
};
