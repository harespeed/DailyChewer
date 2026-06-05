import { Card, Col, Descriptions, List, Row, Space, Tag } from "antd";
import type { DailyReport, QualityScore } from "../api/client";

type Props = {
  report: DailyReport | null;
  qualityScore?: QualityScore | null;
};

function renderItems(items: string[]) {
  return (
    <List
      size="small"
      dataSource={items.length ? items : ["原始日报未提供更多细节"]}
      renderItem={(item) => <List.Item>{item}</List.Item>}
    />
  );
}

export function ReportPreview({ report, qualityScore }: Props) {
  if (!report) return null;
  const resolvedQualityScore = report.quality_score ?? qualityScore ?? null;

  return (
    <Card title="优化日报预览" className="glass-card">
      <Descriptions column={3} size="small">
        <Descriptions.Item label="日期">{report.date}</Descriptions.Item>
        <Descriptions.Item label="星期">{report.weekday}</Descriptions.Item>
        <Descriptions.Item label="周次">{report.week}</Descriptions.Item>
        <Descriptions.Item label="质量评分" span={3}>
          <Space wrap>
            <Tag color="geekblue">{resolvedQualityScore?.total ?? "未生成评分"}</Tag>
            {resolvedQualityScore?.comments?.map((comment) => (
              <Tag key={comment}>{comment}</Tag>
            ))}
          </Space>
        </Descriptions.Item>
      </Descriptions>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card type="inner" title="上午">
            <h4>工作内容</h4>
            {renderItems(report.morning.work_content)}
            <h4>个人成长</h4>
            {renderItems(report.morning.personal_growth)}
            <h4>问题总结</h4>
            {renderItems(report.morning.problems)}
            <h4>解决方案</h4>
            {renderItems(report.morning.solutions)}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card type="inner" title="下午">
            <h4>工作内容</h4>
            {renderItems(report.afternoon.work_content)}
            <h4>个人成长</h4>
            {renderItems(report.afternoon.personal_growth)}
            <h4>问题总结</h4>
            {renderItems(report.afternoon.problems)}
            <h4>解决方案</h4>
            {renderItems(report.afternoon.solutions)}
          </Card>
        </Col>
      </Row>
    </Card>
  );
}
