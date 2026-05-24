import {
  DashboardOutlined,
  ShoppingCartOutlined,
  ShoppingOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { ThemedLayoutV2, ThemedTitleV2 } from "@refinedev/antd";
import "@refinedev/antd/dist/reset.css";
import { Authenticated, Refine } from "@refinedev/core";
import routerBindings, {
  CatchAllNavigate,
  NavigateToResource,
  UnsavedChangesNotifier,
} from "@refinedev/react-router-v6";
import { App as AntdApp, ConfigProvider } from "antd";
import { BrowserRouter, Outlet, Route, Routes } from "react-router-dom";
import { authProvider } from "./providers/authProvider";
import { dataProvider } from "./providers/dataProvider";

import { Dashboard } from "./pages/dashboard";
import { CustomerList } from "./pages/customers/list";
import { OrderList } from "./pages/orders/list";
import { ProductCreate } from "./pages/products/create";
import { ProductEdit } from "./pages/products/edit";
import { ProductList } from "./pages/products/list";
import { LoginPage } from "./pages/login";

const BRAND_COLOR = "#5b3427"; // Pamorya burgundy

export default function App() {
  return (
    <BrowserRouter>
      <ConfigProvider
        theme={{
          token: {
            colorPrimary: BRAND_COLOR,
            borderRadius: 6,
            fontFamily: "'Inter', 'DM Sans', sans-serif",
          },
        }}
      >
        <AntdApp>
          <Refine
            dataProvider={dataProvider}
            authProvider={authProvider}
            routerProvider={routerBindings}
            resources={[
              {
                name: "dashboard",
                list: "/",
                meta: { label: "Dashboard", icon: <DashboardOutlined /> },
              },
              {
                name: "products",
                list: "/products",
                create: "/products/create",
                edit: "/products/:id/edit",
                meta: { label: "Products", icon: <ShoppingOutlined /> },
              },
              {
                name: "orders",
                list: "/orders",
                meta: { label: "Orders", icon: <ShoppingCartOutlined /> },
              },
              {
                name: "customers",
                list: "/customers",
                meta: { label: "Customers", icon: <TeamOutlined /> },
              },
            ]}
            options={{ syncWithLocation: true, warnWhenUnsavedChanges: true }}
          >
            <Routes>
              <Route
                element={
                  <Authenticated
                    key="auth"
                    fallback={<CatchAllNavigate to="/login" />}
                  >
                    <ThemedLayoutV2
                      Title={({ collapsed }) => (
                        <ThemedTitleV2
                          collapsed={collapsed}
                          text="Pamorya Admin"
                        />
                      )}
                    >
                      <Outlet />
                    </ThemedLayoutV2>
                  </Authenticated>
                }
              >
                <Route index element={<Dashboard />} />
                <Route path="/products">
                  <Route index element={<ProductList />} />
                  <Route path="create" element={<ProductCreate />} />
                  <Route path=":id/edit" element={<ProductEdit />} />
                </Route>
                <Route path="/orders" element={<OrderList />} />
                <Route path="/customers" element={<CustomerList />} />
                <Route path="*" element={<NavigateToResource resource="dashboard" />} />
              </Route>

              <Route path="/login" element={<LoginPage />} />
            </Routes>

            <UnsavedChangesNotifier />
          </Refine>
        </AntdApp>
      </ConfigProvider>
    </BrowserRouter>
  );
}
