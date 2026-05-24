import { AuthPage } from "@refinedev/antd";

export const LoginPage: React.FC = () => (
  <AuthPage
    type="login"
    title="Pamorya Admin"
    formProps={{
      initialValues: { password: "" },
    }}
    renderContent={(content) => (
      <div style={{ maxWidth: 360, margin: "0 auto", paddingTop: 80 }}>
        {content}
      </div>
    )}
    // We use password field as the admin key input
    rememberMe={false}
    forgotPasswordLink={false}
    registerLink={false}
  />
);
