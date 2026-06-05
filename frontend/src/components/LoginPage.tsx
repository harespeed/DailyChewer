import { useState } from "react";
import { Button, Card, Form, Input, Segmented, Typography, message } from "antd";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { loginWithPassword, registerUser } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setLoading(true);
    try {
      if (mode === "login") {
        await loginWithPassword(values.username, values.password);
        message.success("登录成功。");
      } else {
        await registerUser(values.username, values.password, values.display_name);
        message.success("注册并登录成功。");
      }
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "登录失败。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <Card className="glass-card login-card">
        <Typography.Text className="eyebrow">DailyChewer</Typography.Text>
        <Typography.Title level={2}>
          {mode === "login" ? "登录后访问你的日报空间" : "注册一个新的日报空间"}
        </Typography.Title>
        <Segmented
          block
          options={[
            { label: "Login", value: "login" },
            { label: "Register", value: "register" },
          ]}
          value={mode}
          onChange={(value) => setMode(value as "login" | "register")}
        />
        <Form layout="vertical" form={form} className="mt-16">
          <Form.Item name="username" label="Username" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          {mode === "register" ? (
            <Form.Item name="display_name" label="Display Name">
              <Input />
            </Form.Item>
          ) : null}
          <Form.Item name="password" label="Password" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" block size="large" loading={loading} onClick={handleSubmit}>
            {mode === "login" ? "Login" : "Register"}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
