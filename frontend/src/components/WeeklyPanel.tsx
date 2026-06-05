import { useState } from "react";
import { Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { downloadProtectedFile, generateWeekly } from "../api/client";

export function WeeklyPanel() {
  const [preview, setPreview] = useState("");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleSubmit = async () => {
    const values = form.getFieldsValue();
    setLoading(true);
    try {
      const result = await generateWeekly({
        week: values.week,
        from_date: values.from_date,
        to_date: values.to_date,
        format: values.format,
        style: values.style,
        project: values.project,
        tags: (values.tags || "").split(",").map((item: string) => item.trim()).filter(Boolean),
        save: true,
      });
      setPreview(result.preview);
      setDownloadUrl(result.download_url || null);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!downloadUrl) return;
    try {
      await downloadProtectedFile(downloadUrl);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "周报下载失败。");
    }
  };

  return (
    <Card className="glass-card" title="生成周报">
      <Form layout="vertical" form={form} initialValues={{ format: "markdown", style: "concise" }}>
        <Form.Item name="week" label="周次">
          <Input placeholder="2026-W23" />
        </Form.Item>
        <Form.Item name="from_date" label="开始日期">
          <Input placeholder="2026-06-01" />
        </Form.Item>
        <Form.Item name="to_date" label="结束日期">
          <Input placeholder="2026-06-07" />
        </Form.Item>
        <Form.Item name="format" label="导出格式">
          <Select options={["markdown", "docx", "xlsx", "csv"].map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item name="style" label="风格">
          <Select options={["concise", "formal", "detailed", "interview"].map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item name="project" label="项目">
          <Input />
        </Form.Item>
        <Form.Item name="tags" label="标签">
          <Input placeholder="automation,api" />
        </Form.Item>
        <Space>
          <Button type="primary" onClick={handleSubmit} loading={loading}>
            Generate Weekly Report
          </Button>
          {downloadUrl ? (
            <Button onClick={() => void handleDownload()}>
              Download
            </Button>
          ) : null}
        </Space>
      </Form>
      {preview ? (
        <Typography.Paragraph className="preview-block">
          <pre>{preview}</pre>
        </Typography.Paragraph>
      ) : null}
    </Card>
  );
}
