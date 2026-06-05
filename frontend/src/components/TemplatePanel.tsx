import { useState } from "react";
import { Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { downloadProtectedFile, generateTemplate } from "../api/client";

export function TemplatePanel() {
  const [result, setResult] = useState<{ file: string; download_url?: string | null } | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleGenerate = async () => {
    setLoading(true);
    try {
      setResult(
        await generateTemplate({
          date: form.getFieldValue("date"),
          format: form.getFieldValue("format"),
        }),
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!result?.download_url) return;
    try {
      await downloadProtectedFile(result.download_url);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || "模板下载失败。");
    }
  };

  return (
    <Card className="glass-card" title="生成日报模板">
      <Form layout="inline" form={form} initialValues={{ format: "markdown" }}>
        <Form.Item name="date" label="日期">
          <Input placeholder="2026-06-03" />
        </Form.Item>
        <Form.Item name="format" label="格式">
          <Select options={["markdown", "csv", "xlsx", "docx"].map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Space>
          <Button type="primary" onClick={handleGenerate} loading={loading}>
            Generate Template
          </Button>
          {result?.download_url ? (
            <Button onClick={() => void handleDownload()}>
              Download
            </Button>
          ) : null}
        </Space>
      </Form>
      {result ? (
        <Typography.Paragraph className="mt-16">
          模板路径：{result.file}
        </Typography.Paragraph>
      ) : null}
    </Card>
  );
}
