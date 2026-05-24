import {
  AlertOutlined,
  DollarOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Card, Col, Row, Spin, Statistic, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import type { DashboardStats } from "../../interfaces";
import { apiClient } from "../../providers/dataProvider";

const { Title } = Typography;

const STATUS_COLORS: Record<string, string> = {
  Paid: "#52c41a",
  Shipped: "#1677ff",
  Pending: "#fa8c16",
  Draft: "#8c8c8c",
  Cancelled: "#ff4d4f",
};

const PIE_PALETTE = ["#52c41a", "#1677ff", "#fa8c16", "#8c8c8c", "#ff4d4f", "#722ed1"];

export const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .get("/admin/dashboard")
      .then((r) => setStats(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!stats) return <div>Failed to load dashboard.</div>;

  const pieData = Object.entries(stats.orders_by_status).map(([name, value]) => ({
    name,
    value,
  }));

  const topProductColumns = [
    { title: "#", dataIndex: "rank", key: "rank", width: 40 },
    { title: "Product", dataIndex: "name", key: "name" },
    {
      title: "Units Sold",
      dataIndex: "quantity",
      key: "quantity",
      render: (v: number) => <strong>{v}</strong>,
    },
  ];

  const topProductData = stats.top_products.map((p, i) => ({
    key: i,
    rank: i + 1,
    name: p.name,
    quantity: p.quantity,
  }));

  return (
    <div style={{ padding: "0 4px" }}>
      <Title level={4} style={{ marginBottom: 24 }}>
        Dashboard
      </Title>

      {/* KPI Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Total Revenue"
              value={stats.total_revenue}
              prefix={<DollarOutlined />}
              suffix="LKR"
              precision={0}
              valueStyle={{ color: "#3f8600" }}
              formatter={(v) => Number(v).toLocaleString()}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Orders Today"
              value={stats.orders_today}
              prefix={<ShoppingCartOutlined />}
              valueStyle={{ color: "#1677ff" }}
            />
            <div style={{ color: "#888", marginTop: 4, fontSize: 13 }}>
              {stats.total_orders} total
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Low Stock Items"
              value={stats.low_stock_count}
              prefix={<AlertOutlined />}
              valueStyle={{ color: stats.low_stock_count > 0 ? "#fa8c16" : "#3f8600" }}
            />
            <div style={{ color: "#888", marginTop: 4, fontSize: 13 }}>
              {stats.out_of_stock_count} out of stock
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Customers"
              value={stats.total_customers}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Charts row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={16}>
          <Card title="Revenue — Last 7 Days (LKR)">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={stats.revenue_last_7_days}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(d) => d.slice(5)} // MM-DD
                  tick={{ fontSize: 12 }}
                />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v: number) => [`LKR ${v.toLocaleString()}`, "Revenue"]} />
                <Line
                  type="monotone"
                  dataKey="revenue"
                  stroke="#5b3427"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="Orders by Status">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={false}
                >
                  {pieData.map((entry, i) => (
                    <Cell
                      key={entry.name}
                      fill={STATUS_COLORS[entry.name] ?? PIE_PALETTE[i % PIE_PALETTE.length]}
                    />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* Top products */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Top 5 Products by Units Sold">
            <Table
              dataSource={topProductData}
              columns={topProductColumns}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="Order Status Breakdown">
            <Row gutter={[8, 8]}>
              {Object.entries(stats.orders_by_status).map(([status, count]) => (
                <Col key={status} span={12}>
                  <div
                    style={{
                      background: "#fafafa",
                      border: "1px solid #f0f0f0",
                      borderRadius: 8,
                      padding: "12px 16px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <Tag color={STATUS_COLORS[status] ?? "default"}>{status}</Tag>
                    <strong style={{ fontSize: 18 }}>{count}</strong>
                  </div>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>
    </div>
  );
};
