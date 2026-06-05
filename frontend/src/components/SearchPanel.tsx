import { useState } from "react";
import { Button, Card, Form, Input, Table } from "antd";
import { searchReports, type SearchResult } from "../api/client";

export function SearchPanel() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleSearch = async () => {
    setLoading(true);
    try {
      setResults(
        await searchReports({
          q: form.getFieldValue("q"),
          week: form.getFieldValue("week"),
          from_date: form.getFieldValue("from_date"),
          to_date: form.getFieldValue("to_date"),
          project: form.getFieldValue("project"),
          tag: form.getFieldValue("tag"),
          limit: Number(form.getFieldValue("limit") || 10),
        }),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="glass-card" title="搜索历史日报">
      <Form className="search-form-grid" layout="vertical" form={form} initialValues={{ limit: 10 }}>
        <Form.Item name="q" label="关键词">
          <Input placeholder="错误码" />
        </Form.Item>
        <Form.Item name="week" label="周次">
          <Input />
        </Form.Item>
        <Form.Item name="from_date" label="开始日期">
          <Input />
        </Form.Item>
        <Form.Item name="to_date" label="结束日期">
          <Input />
        </Form.Item>
        <Form.Item name="project" label="项目">
          <Input />
        </Form.Item>
        <Form.Item name="tag" label="标签">
          <Input />
        </Form.Item>
        <Form.Item name="limit" label="数量">
          <Input />
        </Form.Item>
        <Form.Item label=" ">
          <Button type="primary" block onClick={handleSearch} loading={loading}>
            Search
          </Button>
        </Form.Item>
      </Form>
      <Table
        className="mt-16"
        rowKey={(record) => `${record.date}-${record.matched_section}-${record.optimized_file}`}
        loading={loading}
        dataSource={results}
        scroll={{ x: 900 }}
        columns={[
          { title: "Date", dataIndex: "date" },
          { title: "Week", dataIndex: "week" },
          { title: "Section", dataIndex: "matched_section" },
          { title: "Snippet", dataIndex: "snippet" },
          { title: "Optimized File", dataIndex: "optimized_file" },
        ]}
      />
    </Card>
  );
}
