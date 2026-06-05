import { Button, Layout, Space, Spin, Tabs, Typography } from "antd";
import { useAuth } from "./auth/AuthContext";
import { LoginPage } from "./components/LoginPage";
import { FileDropzone } from "./components/FileDropzone";
import { ReportsPanel } from "./components/ReportsPanel";
import { WeeklyPanel } from "./components/WeeklyPanel";
import { MonthlyPanel } from "./components/MonthlyPanel";
import { SearchPanel } from "./components/SearchPanel";
import { DoctorPanel } from "./components/DoctorPanel";
import { TemplatePanel } from "./components/TemplatePanel";
import { AccountPanel } from "./components/AccountPanel";
import { AdminUsersPanel } from "./components/AdminUsersPanel";
import { ReleaseNotesButton } from "./components/ReleaseNotesButton";
import { DailyNotesDashboard } from "./components/DailyNotesDashboard";
import { WallpaperBackdrop } from "./components/WallpaperBackdrop";
import { UsageGuideButton } from "./components/UsageGuideButton";

export default function App() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return (
      <div className="center-shell">
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  const items = [
    {
      key: "home",
      label: "Daily Notes",
      children: <DailyNotesDashboard />,
    },
    {
      key: "upload",
      label: "Upload Daily",
      children: <FileDropzone onSaved={() => undefined} />,
    },
    { key: "reports", label: "Reports", children: <ReportsPanel /> },
    { key: "weekly", label: "Weekly", children: <WeeklyPanel /> },
    { key: "monthly", label: "Monthly", children: <MonthlyPanel /> },
    { key: "search", label: "Search", children: <SearchPanel /> },
    { key: "template", label: "Template", children: <TemplatePanel /> },
    { key: "account", label: "Account", children: <AccountPanel /> },
    ...(user.is_admin
      ? [
          { key: "doctor", label: "Doctor", children: <DoctorPanel /> },
          { key: "admin-users", label: "Admin Users", children: <AdminUsersPanel /> },
        ]
      : []),
  ];

  return (
    <Layout className="app-shell">
      <WallpaperBackdrop />
      <div className="hero">
        <Space className="hero-top" align="start">
          <div>
            <Typography.Text className="eyebrow">DailyChewer</Typography.Text>
            <Typography.Title level={1}>日报优化、周报月报与检索，一套入口。</Typography.Title>
          </div>
          <div className="hero-user">
            <UsageGuideButton isAdmin={user.is_admin} />
            <ReleaseNotesButton />
            <Typography.Text>{user.display_name || user.username}</Typography.Text>
            <Button className="hero-action-button" onClick={logout}>Logout</Button>
          </div>
        </Space>
        <Typography.Paragraph>
          当前所有数据都绑定到登录用户。CLI 和 Web API 仍共享同一套 backend services。
        </Typography.Paragraph>
      </div>
      <Tabs className="app-tabs" items={items} />
    </Layout>
  );
}
