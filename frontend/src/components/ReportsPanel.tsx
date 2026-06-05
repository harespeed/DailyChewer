import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Space, Table } from "antd";
import { fetchReports, type ReportIndexItem } from "../api/client";

export function ReportsPanel() {
  const [data, setData] = useState<ReportIndexItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      setData(await fetchReports(form.getFieldsValue()));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <Card className="glass-card" title="日报列表">
      <Form layout="inline" form={form} onFinish={load}>
        <Form.Item name="week" label="周次">
          <Input placeholder="2026-W23" />
        </Form.Item>
        <Form.Item name="project" label="项目">
          <Input placeholder="AI-App" />
        </Form.Item>
        <Form.Item name="tag" label="标签">
          <Input placeholder="automation" />
        </Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" loading={loading}>
            Refresh
          </Button>
        </Space>
      </Form>
      <Table
        className="mt-16"
        rowKey={(record) => `${record.date}-${record.optimized_file}`}
        loading={loading}
        dataSource={data}
        scroll={{ x: 960 }}
        columns={[
          { title: "Date", dataIndex: "date" },
          { title: "Weekday", dataIndex: "weekday" },
          { title: "Week", dataIndex: "week" },
          { title: "Project", dataIndex: "project" },
          { title: "Tags", dataIndex: "tags", render: (value: string[]) => value?.join(", ") || "-" },
          { title: "Quality", dataIndex: "quality_score" },
          { title: "Optimized File", dataIndex: "optimized_file" },
        ]}
      />
    </Card>
  );
}
