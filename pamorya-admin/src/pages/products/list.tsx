import {
  CreateButton,
  DeleteButton,
  EditButton,
  FilterDropdown,
  List,
  useTable,
} from "@refinedev/antd";
import { Image, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { Product } from "../../interfaces";
import { CATEGORIES } from "../../interfaces";

const { Text } = Typography;

export const ProductList: React.FC = () => {
  const { tableProps, searchFormProps, setFilters } = useTable<Product>({
    resource: "products",
    pagination: { pageSize: 20 },
    syncWithLocation: true,
  });

  const handleCategoryChange = (value: string) => {
    setFilters([{ field: "category", operator: "eq", value }]);
  };

  const handleSearch = (value: string) => {
    setFilters([{ field: "search", operator: "contains", value }]);
  };

  return (
    <List
      headerButtons={
        <Space>
          <Input.Search
            placeholder="Search products…"
            allowClear
            onSearch={handleSearch}
            style={{ width: 220 }}
          />
          <Select
            allowClear
            placeholder="Filter category"
            style={{ width: 180 }}
            onChange={handleCategoryChange}
            options={CATEGORIES.map((c) => ({ label: c, value: c }))}
          />
          <CreateButton />
        </Space>
      }
    >
      <Table
        {...tableProps}
        rowKey="id"
        scroll={{ x: 900 }}
        expandable={{
          expandedRowRender: (record: Product) => (
            <Table
              dataSource={record.inventory}
              rowKey="id"
              pagination={false}
              size="small"
              style={{ margin: 0 }}
              columns={[
                { title: "Size", dataIndex: "size", key: "size" },
                {
                  title: "Stock",
                  dataIndex: "stock_quantity",
                  key: "stock_quantity",
                  render: (v: number) => (
                    <Tag color={v === 0 ? "red" : v <= 3 ? "orange" : "green"}>
                      {v === 0 ? "Out of Stock" : `${v} left`}
                    </Tag>
                  ),
                },
              ]}
            />
          ),
        }}
      >
        <Table.Column
          title="Image"
          dataIndex="image_url"
          key="image_url"
          width={80}
          render={(url: string | null) =>
            url ? (
              <Image
                src={url.split(",")[0].trim()}
                alt="product"
                width={60}
                height={60}
                style={{ objectFit: "cover", borderRadius: 6 }}
                preview={{ src: url.split(",")[0].trim() }}
              />
            ) : (
              <div
                style={{
                  width: 60,
                  height: 60,
                  background: "#f5f5f5",
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#ccc",
                  fontSize: 11,
                }}
              >
                No img
              </div>
            )
          }
        />
        <Table.Column
          title="Name"
          dataIndex="product_name"
          key="product_name"
          render={(name: string, record: Product) => (
            <div>
              <Text strong>{name}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.colour}
              </Text>
            </div>
          )}
        />
        <Table.Column
          title="Category"
          dataIndex="category"
          key="category"
          render={(cat: string) => <Tag>{cat}</Tag>}
        />
        <Table.Column
          title="Price (LKR)"
          dataIndex="price"
          key="price"
          align="right"
          render={(v: number) => v.toLocaleString()}
        />
        <Table.Column
          title="Stock"
          dataIndex="total_stock"
          key="total_stock"
          align="center"
          render={(v: number) => (
            <Tag color={v === 0 ? "red" : v <= 5 ? "orange" : "green"}>
              {v === 0 ? "Out of Stock" : `${v} units`}
            </Tag>
          )}
        />
        <Table.Column
          title="Actions"
          key="actions"
          fixed="right"
          width={120}
          render={(_: unknown, record: Product) => (
            <Space>
              <EditButton hideText size="small" recordItemId={record.id} />
              <DeleteButton
                hideText
                size="small"
                recordItemId={record.id}
                confirmTitle="Archive product?"
                confirmOkText="Archive"
                successNotification={{
                  message: "Product archived (stock set to 0)",
                  type: "success",
                }}
              />
            </Space>
          )}
        />
      </Table>
    </List>
  );
};
