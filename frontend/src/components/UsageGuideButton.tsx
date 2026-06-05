import { Button, Popover, Typography } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";

const baseGuideSections = [
  {
    title: "Daily Notes",
    items: [
      "保存便条：写下当天记录，选择上午/下午后保存。",
      "日期格子：点击选择当天；按住 Shift 再点另一天，可选择一段日期。",
      "生成并优化日报：把当前日期的便条整理成日报并保存。",
      "生成并优化周报/阶段报：单日模式生成所在周周报；范围模式生成所选日期段阶段报。",
    ],
  },
  {
    title: "Upload Daily",
    items: [
      "Preview & Optimize：上传日报文件后生成结构化预览。",
      "Optimize：回答某条追问后，只重新优化这条追问对应内容。",
      "Save Report：确认预览后保存为正式日报。",
    ],
  },
  {
    title: "Reports / Weekly / Monthly",
    items: [
      "Reports：查看已保存日报。",
      "Weekly：按周或日期范围生成周报。",
      "Monthly：按月份生成月报。",
    ],
  },
  {
    title: "其他入口",
    items: [
      "Search：搜索历史日报内容。",
      "Template：生成当天日报模板。",
      "Account：修改当前账号密码。",
    ],
  },
];

const adminGuideSection = {
  title: "系统维护",
  items: [
    "Doctor：检查系统配置、数据库和 LLM 连接状态。",
    "Admin Users：查看用户列表并管理用户状态。",
  ],
};

function UsageGuideContent({ isAdmin }: { isAdmin: boolean }) {
  const guideSections = isAdmin ? [...baseGuideSections, adminGuideSection] : baseGuideSections;

  return (
    <div className="usage-guide-panel">
      {guideSections.map((section) => (
        <div className="usage-guide-section" key={section.title}>
          <Typography.Title level={5}>{section.title}</Typography.Title>
          <ul className="usage-guide-list">
            {section.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function UsageGuideButton({ isAdmin = false }: { isAdmin?: boolean }) {
  return (
    <Popover
      placement="bottomRight"
      trigger="hover"
      mouseEnterDelay={0.12}
      mouseLeaveDelay={0.18}
      overlayClassName="usage-guide-popover"
      content={<UsageGuideContent isAdmin={isAdmin} />}
    >
      <Button icon={<QuestionCircleOutlined />} className="hero-action-button">
        使用说明
      </Button>
    </Popover>
  );
}
