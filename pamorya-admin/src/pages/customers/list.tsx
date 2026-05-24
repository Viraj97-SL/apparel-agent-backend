import { List, useTable } from "@refinedev/antd";
import { Table, Tag, Typography } from "antd";
import type { Customer } from "../../interfaces";

const { Text } = Typography;

export const CustomerList: React.FC = () => {
  const { tableProps } = useTable<Customer>({
    resource: "customers",
    pagination: { pageSize: 20 },
    syncWithLocation: true,
  });

  return (
    <List canCreate={false}>
      <Table {...tableProps} rowKey="id" scroll={{ x: 800 }}>
        <Table.Column
          title="Name"
          dataIndex="full_name"
          key="full_name"
          render={(v: string) => <Text strong>{v}</Text>}
        />
        <Table.Column title="Email" dataIndex="email" key="email" />
        <Table.Column title="Phone" dataIndex="phone_number" key="phone_number" />
        <Table.Column
          title="Address"
          dataIndex="shipping_address"
          key="shipping_address"
          ellipsis
        />
        <Table.Column
          title="Orders"
          dataIndex="order_count"
          key="order_count"
          align="center"
          render={(v: number) => (
            <Tag color={v > 0 ? "blue" : "default"}>{v}</Tag>
          )}
        />
        <Table.Column
          title="Total Spent (LKR)"
          dataIndex="total_spent"
          key="total_spent"
          align="right"
          render={(v: number) => (
            <Text strong style={{ color: v > 0 ? "#3f8600" : undefined }}>
              {v.toLocaleString()}
            </Text>
          )}
        />
        <Table.Column
          title="Joined"
          dataIndex="created_at"
          key="created_at"
          render={(v: string | null) =>
            v ? new Date(v).toLocaleDateString("en-GB") : "—"
          }
        />
      </Table>
    </List>
  );
};
