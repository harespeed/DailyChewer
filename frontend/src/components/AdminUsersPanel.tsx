import { useEffect, useState } from "react";
import { Button, Card, Space, Table, Tag, message } from "antd";
import { fetchUsers, type UserRead, updateUserStatus } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function AdminUsersPanel() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<UserRead[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      setUsers(await fetchUsers());
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "加载用户列表失败。");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.is_admin) {
      void load();
    }
  }, [user?.is_admin]);

  const handleToggle = async (record: UserRead) => {
    try {
      await updateUserStatus(record.id, !record.is_active);
      message.success("用户状态已更新。");
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "更新用户状态失败。");
    }
  };

  if (!user?.is_admin) {
    return null;
  }

  return (
    <Card className="glass-card" title="Admin Users">
      <Table
        rowKey="id"
        loading={loading}
        dataSource={users}
        scroll={{ x: 980 }}
        columns={[
          { title: "Username", dataIndex: "username" },
          { title: "Display Name", dataIndex: "display_name" },
          {
            title: "Active",
            dataIndex: "is_active",
            render: (value: boolean) => <Tag color={value ? "green" : "red"}>{String(value)}</Tag>,
          },
          {
            title: "Admin",
            dataIndex: "is_admin",
            render: (value: boolean) => <Tag color={value ? "blue" : "default"}>{String(value)}</Tag>,
          },
          { title: "Created", dataIndex: "created_at" },
          {
            title: "Action",
            render: (_: unknown, record: UserRead) => (
              <Space>
                <Button
                  disabled={record.id === user.id && record.is_active}
                  onClick={() => void handleToggle(record)}
                >
                  {record.is_active ? "Disable" : "Enable"}
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
