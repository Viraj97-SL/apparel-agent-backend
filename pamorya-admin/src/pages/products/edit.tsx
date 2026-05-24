import {
  DeleteOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { Edit, useForm } from "@refinedev/antd";
import { useNotification } from "@refinedev/core";
import {
  Button,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { CloudinaryUpload } from "../../components/CloudinaryUpload";
import type { InventoryRow, Product } from "../../interfaces";
import { CATEGORIES } from "../../interfaces";
import { apiClient } from "../../providers/dataProvider";

const { Title } = Typography;

export const ProductEdit: React.FC = () => {
  const { id } = useParams();
  const { open: notify } = useNotification();

  const { formProps, saveButtonProps, queryResult } = useForm<Product>({
    resource: "products",
    action: "edit",
    id,
    metaData: { id },
  });

  const product = queryResult?.data?.data as Product | undefined;
  const [inventory, setInventory] = useState<InventoryRow[]>([]);
  const [addSize, setAddSize] = useState("");
  const [addQty, setAddQty] = useState(0);
  const [addLoading, setAddLoading] = useState(false);

  // Sync local inventory state when query loads
  if (product && inventory.length === 0 && product.inventory.length > 0) {
    setInventory(product.inventory);
  }

  const handleQtyChange = async (invId: number, newQty: number) => {
    try {
      await apiClient.patch(`/admin/inventory/${invId}`, {
        stock_quantity: newQty,
      });
      setInventory((prev) =>
        prev.map((r) => (r.id === invId ? { ...r, stock_quantity: newQty } : r))
      );
      notify?.({ type: "success", message: "Stock updated", description: "" });
    } catch {
      notify?.({ type: "error", message: "Failed to update stock", description: "" });
    }
  };

  const handleDeleteRow = async (invId: number) => {
    try {
      await apiClient.delete(`/admin/inventory/${invId}`);
      setInventory((prev) => prev.filter((r) => r.id !== invId));
      notify?.({ type: "success", message: "Size removed", description: "" });
    } catch {
      notify?.({ type: "error", message: "Failed to remove size", description: "" });
    }
  };

  const handleAddRow = async () => {
    if (!addSize.trim() || !id) return;
    setAddLoading(true);
    try {
      const { data } = await apiClient.post("/admin/inventory", {
        product_id: Number(id),
        size: addSize.trim().toUpperCase(),
        stock_quantity: addQty,
      });
      setInventory((prev) => [...prev, data]);
      setAddSize("");
      setAddQty(0);
      notify?.({ type: "success", message: "Size added", description: "" });
    } catch {
      notify?.({ type: "error", message: "Failed to add size", description: "" });
    } finally {
      setAddLoading(false);
    }
  };

  const inventoryColumns = [
    {
      title: "Size",
      dataIndex: "size",
      key: "size",
      width: 100,
      render: (s: string) => <Tag>{s}</Tag>,
    },
    {
      title: "Stock Qty",
      dataIndex: "stock_quantity",
      key: "stock_quantity",
      render: (qty: number, record: InventoryRow) => (
        <InputNumber
          min={0}
          value={qty}
          style={{ width: 100 }}
          onChange={(v) => {
            if (v !== null) handleQtyChange(record.id, v);
          }}
        />
      ),
    },
    {
      title: "Status",
      key: "status",
      render: (_: unknown, record: InventoryRow) => (
        <Tag
          color={
            record.stock_quantity === 0
              ? "red"
              : record.stock_quantity <= 3
              ? "orange"
              : "green"
          }
        >
          {record.stock_quantity === 0
            ? "Out of Stock"
            : record.stock_quantity <= 3
            ? "Low Stock"
            : "In Stock"}
        </Tag>
      ),
    },
    {
      title: "",
      key: "delete",
      width: 60,
      render: (_: unknown, record: InventoryRow) => (
        <Popconfirm
          title="Remove this size?"
          onConfirm={() => handleDeleteRow(record.id)}
          okText="Remove"
          okType="danger"
        >
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            size="small"
          />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Edit saveButtonProps={saveButtonProps}>
      <Form {...formProps} layout="vertical">
        <Row gutter={24}>
          <Col xs={24} lg={12}>
            <Form.Item
              label="Product Name"
              name="product_name"
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>

            <Form.Item label="Colour" name="colour" rules={[{ required: true }]}>
              <Input />
            </Form.Item>

            <Form.Item label="Category" name="category" rules={[{ required: true }]}>
              <Select
                options={CATEGORIES.map((c) => ({ label: c, value: c }))}
              />
            </Form.Item>

            <Form.Item label="Price (LKR)" name="price" rules={[{ required: true }]}>
              <InputNumber style={{ width: "100%" }} min={0} />
            </Form.Item>
          </Col>

          <Col xs={24} lg={12}>
            <Form.Item label="Product Image" name="image_url">
              <CloudinaryUpload />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item label="Description" name="description">
          <Input.TextArea rows={4} />
        </Form.Item>
      </Form>

      {/* Inventory section — independent of Refine form */}
      <Divider />
      <Title level={5}>Inventory</Title>

      <Table
        dataSource={inventory}
        columns={inventoryColumns}
        rowKey="id"
        pagination={false}
        size="small"
        style={{ marginBottom: 16 }}
      />

      {/* Add new size row */}
      <Space>
        <Input
          placeholder="Size (e.g. M)"
          value={addSize}
          onChange={(e) => setAddSize(e.target.value)}
          style={{ width: 100 }}
        />
        <InputNumber
          min={0}
          value={addQty}
          onChange={(v) => setAddQty(v ?? 0)}
          placeholder="Qty"
          style={{ width: 80 }}
        />
        <Button
          type="dashed"
          icon={<PlusOutlined />}
          onClick={handleAddRow}
          loading={addLoading}
          disabled={!addSize.trim()}
        >
          Add Size
        </Button>
      </Space>
    </Edit>
  );
};
