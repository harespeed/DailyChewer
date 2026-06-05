import { useState } from "react";
import { Alert, Button, Card, Descriptions, Form, Input, message } from "antd";
import { changePassword } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function AccountPanel() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleChangePassword = async () => {
    const values = await form.validateFields();
    setLoading(true);
    try {
      await changePassword({
        old_password: values.old_password,
        new_password: values.new_password,
      });
      form.resetFields();
      message.success("密码已更新。");
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "修改密码失败。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="stack">
      <Card className="glass-card" title="Account">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Username">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="Display Name">{user?.display_name || "-"}</Descriptions.Item>
          <Descriptions.Item label="Admin">{String(!!user?.is_admin)}</Descriptions.Item>
          <Descriptions.Item label="Active">{String(!!user?.is_active)}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card className="glass-card" title="Change Password">
        <Alert type="info" showIcon message="修改密码后，当前 token 仍可继续使用，直到再次登录或过期。" />
        <Form layout="vertical" form={form} className="mt-16">
          <Form.Item name="old_password" label="Old Password" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="new_password" label="New Password" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" loading={loading} onClick={() => void handleChangePassword()}>
            Change Password
          </Button>
        </Form>
      </Card>
    </div>
  );
}
