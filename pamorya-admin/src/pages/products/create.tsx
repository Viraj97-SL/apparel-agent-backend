import { Create, useForm } from "@refinedev/antd";
import { Col, Form, Input, InputNumber, Row, Select } from "antd";
import { CloudinaryUpload } from "../../components/CloudinaryUpload";
import { CATEGORIES } from "../../interfaces";

export const ProductCreate: React.FC = () => {
  const { formProps, saveButtonProps } = useForm({ resource: "products" });

  return (
    <Create saveButtonProps={saveButtonProps}>
      <Form {...formProps} layout="vertical">
        <Row gutter={24}>
          <Col xs={24} lg={12}>
            <Form.Item
              label="Product Name"
              name="product_name"
              rules={[{ required: true, message: "Required" }]}
            >
              <Input placeholder="e.g. Midnight Velvet Dream" />
            </Form.Item>

            <Form.Item
              label="Colour"
              name="colour"
              rules={[{ required: true, message: "Required" }]}
            >
              <Input placeholder="e.g. Navy Blue" />
            </Form.Item>

            <Form.Item
              label="Category"
              name="category"
              rules={[{ required: true, message: "Required" }]}
            >
              <Select
                options={CATEGORIES.map((c) => ({ label: c, value: c }))}
                placeholder="Select category"
              />
            </Form.Item>

            <Form.Item
              label="Price (LKR)"
              name="price"
              rules={[{ required: true, message: "Required" }]}
            >
              <InputNumber style={{ width: "100%" }} min={0} placeholder="e.g. 4500" />
            </Form.Item>
          </Col>

          <Col xs={24} lg={12}>
            <Form.Item label="Product Image" name="image_url">
              <CloudinaryUpload />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          label="Description"
          name="description"
          rules={[{ required: true, message: "Required" }]}
        >
          <Input.TextArea rows={4} placeholder="Product description…" />
        </Form.Item>
      </Form>
    </Create>
  );
};
