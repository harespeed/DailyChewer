import { useEffect, useState } from "react";
import { Button, Card, Table, Tag } from "antd";
import { fetchDoctor, type DoctorCheckItem } from "../api/client";

export function DoctorPanel() {
  const [checks, setChecks] = useState<DoctorCheckItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async (checkApi = false) => {
    setLoading(true);
    try {
      const result = await fetchDoctor(checkApi);
      setChecks(result.checks);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(false);
  }, []);

  return (
    <Card
      className="glass-card"
      title="Doctor"
      extra={
        <Button onClick={() => void load(true)} loading={loading}>
          Check API
        </Button>
      }
    >
      <Table
        rowKey="name"
        loading={loading}
        dataSource={checks}
        columns={[
          { title: "Check", dataIndex: "name" },
          {
            title: "Status",
            dataIndex: "status",
            render: (value: string) => (
              <Tag color={value === "OK" ? "green" : value === "WARN" ? "gold" : "red"}>{value}</Tag>
            ),
          },
          { title: "Value", dataIndex: "value" },
          { title: "Details", dataIndex: "details" },
        ]}
      />
    </Card>
  );
}
