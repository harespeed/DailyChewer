import { useState } from "react";
import { Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { downloadProtectedFile, generateMonthly } from "../api/client";

export function MonthlyPanel() {
  const [preview, setPreview] = useState("");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleSubmit = async () => {
    const values = form.getFieldsValue();
    setLoading(true);
    try {
      const result = await generateMonthly({
        month: values.month,
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
      message.error(error?.response?.data?.detail || "月报下载失败。");
    }
  };

  return (
    <Card className="glass-card" title="生成月报">
      <Form layout="vertical" form={form} initialValues={{ format: "markdown", style: "formal" }}>
        <Form.Item name="month" label="月份">
          <Input placeholder="2026-06" />
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
            Generate Monthly Report
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
