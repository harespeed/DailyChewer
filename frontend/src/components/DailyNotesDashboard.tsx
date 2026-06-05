import { Button, Empty, Input, Popover, Select, Space, Spin, Tag, Typography, message } from "antd";
import { DownloadOutlined, FileTextOutlined, SaveOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import {
  DailyNote,
  DailyNoteDay,
  createDailyNote,
  deleteDailyNote,
  downloadProtectedFile,
  fetchDailyNotes,
  generateDailyFromNotes,
  generateWeeklyFromNotes,
  updateDailyNote,
} from "../api/client";
import { FloatingErrorButton, createFloatingErrorEntry, type FloatingErrorEntry } from "./FloatingErrorButton";

const weekdayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const periodLabels: Record<string, string> = {
  morning: "上午",
  afternoon: "下午",
};

function toDateKey(date: Date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function monthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function buildMonthCells(viewDate: Date) {
  const first = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const cell = new Date(start);
    cell.setDate(start.getDate() + index);
    return cell;
  });
}

function currentPeriod() {
  return new Date().getHours() < 12 ? "morning" : "afternoon";
}

function notePreview(day?: DailyNoteDay) {
  if (!day) {
    return <Typography.Text type="secondary">No note yet.</Typography.Text>;
  }
  return (
    <div className="note-popover">
      <Typography.Text strong>{day.date}</Typography.Text>
      {day.notes.map((note) => (
        <div className="note-popover-item" key={note.id}>
          <Tag color="green">{periodLabels[note.period] || note.period}</Tag>
          <Typography.Paragraph ellipsis={{ rows: 4 }}>{note.content}</Typography.Paragraph>
        </div>
      ))}
    </div>
  );
}

function getNotesErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (detail === "Not Found" || error?.response?.status === 404) {
    return "Calendar 便条接口返回 Not Found。请确认后端已重启到最新代码，并已执行数据库迁移 `alembic upgrade head`。";
  }
  if (typeof detail === "string") {
    return detail;
  }
  return error?.message || fallback;
}

export function DailyNotesDashboard() {
  const [viewDate, setViewDate] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState(() => toDateKey(new Date()));
  const [days, setDays] = useState<DailyNoteDay[]>([]);
  const [noteText, setNoteText] = useState("");
  const [period, setPeriod] = useState(() => currentPeriod());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generatingDaily, setGeneratingDaily] = useState(false);
  const [generatingWeekly, setGeneratingWeekly] = useState(false);
  const [dailyResult, setDailyResult] = useState<{ optimized_file?: string | null } | null>(null);
  const [weeklyResult, setWeeklyResult] = useState<{ download_url?: string | null; file?: string | null } | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [errorEntries, setErrorEntries] = useState<FloatingErrorEntry[]>([]);
  const [errorPopoverOpen, setErrorPopoverOpen] = useState(false);

  const selectedMonth = monthKey(viewDate);
  const cells = useMemo(() => buildMonthCells(viewDate), [viewDate]);
  const dayMap = useMemo(() => new Map(days.map((day) => [day.date, day])), [days]);
  const selectedDay = dayMap.get(selectedDate);

  const notifyError = (error: any, fallback: string) => {
    const errorMessage = getNotesErrorMessage(error, fallback);
    setErrorEntries((current) => [createFloatingErrorEntry(errorMessage), ...current].slice(0, 20));
    message.error(errorMessage);
  };

  const loadNotes = async () => {
    setLoading(true);
    try {
      const payload = await fetchDailyNotes(selectedMonth);
      setDays(payload.days);
    } catch (error: any) {
      notifyError(error, "Failed to load notes.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNotes();
  }, [selectedMonth]);

  useEffect(() => {
    const nextEditing: Record<string, string> = {};
    selectedDay?.notes.forEach((note) => {
      nextEditing[note.id] = note.content;
    });
    setEditing(nextEditing);
  }, [selectedDay]);

  const addNote = async () => {
    setSaving(true);
    try {
      await createDailyNote({ content: noteText, date: selectedDate, period });
      setNoteText("");
      await loadNotes();
      message.success("Note saved.");
    } catch (error: any) {
      notifyError(error, "Failed to save note.");
    } finally {
      setSaving(false);
    }
  };

  const saveExisting = async (note: DailyNote) => {
    try {
      await updateDailyNote(note.id, { content: editing[note.id] || "", period: note.period });
      await loadNotes();
      message.success("Note updated.");
    } catch (error: any) {
      notifyError(error, "Failed to update note.");
    }
  };

  const removeNote = async (note: DailyNote) => {
    try {
      await deleteDailyNote(note.id);
      await loadNotes();
      message.success("Note deleted.");
    } catch (error: any) {
      notifyError(error, "Failed to delete note.");
    }
  };

  const generateDaily = async () => {
    setGeneratingDaily(true);
    try {
      const result = await generateDailyFromNotes(selectedDate);
      setDailyResult(result);
      message.success("Daily report generated.");
    } catch (error: any) {
      notifyError(error, "Failed to generate daily report.");
    } finally {
      setGeneratingDaily(false);
    }
  };

  const generateWeekly = async () => {
    setGeneratingWeekly(true);
    try {
      const result = await generateWeeklyFromNotes(selectedDate);
      setWeeklyResult(result);
      message.success("Weekly report generated.");
    } catch (error: any) {
      notifyError(error, "Failed to generate weekly report.");
    } finally {
      setGeneratingWeekly(false);
    }
  };

  const shiftMonth = (offset: number) => {
    setViewDate((current) => new Date(current.getFullYear(), current.getMonth() + offset, 1));
  };

  return (
    <div className="notes-dashboard">
      <div className="note-action-rail">
        <Button
          type="primary"
          icon={<FileTextOutlined />}
          disabled={!selectedDay}
          loading={generatingDaily}
          onClick={generateDaily}
        >
          生成并优化日报
        </Button>
        <Button disabled={!dailyResult} loading={generatingWeekly} onClick={generateWeekly}>
          生成并优化周报
        </Button>
        {weeklyResult?.download_url ? (
          <Button icon={<DownloadOutlined />} onClick={() => downloadProtectedFile(weeklyResult.download_url || "")}>
            下载周报
          </Button>
        ) : null}
      </div>

      <section className="glass-card note-compose">
        <div>
          <Typography.Text className="eyebrow">Daily note</Typography.Text>
          <Typography.Title level={3}>写一条便条，系统会自动绑定日期和上午/下午。</Typography.Title>
          <Typography.Text type="secondary">
            当前选择：{selectedDate} · {periodLabels[period]} · {new Date(`${selectedDate}T00:00:00`).toLocaleDateString(undefined, { weekday: "long" })}
          </Typography.Text>
        </div>
        <Input.TextArea
          rows={5}
          value={noteText}
          onChange={(event) => setNoteText(event.target.value)}
          placeholder="写下今天发生了什么、卡点、推进进展或临时想到的成长总结。"
        />
        <Space wrap>
          <Select
            value={period}
            onChange={setPeriod}
            options={[
              { value: "morning", label: "上午" },
              { value: "afternoon", label: "下午" },
            ]}
          />
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={addNote}>
            保存便条
          </Button>
        </Space>
      </section>

      <section className="glass-card note-calendar-shell">
        <div className="note-calendar-head">
          <div>
            <Typography.Text className="eyebrow">Calendar</Typography.Text>
            <Typography.Title level={3}>{selectedMonth}</Typography.Title>
          </div>
          <Space>
            <Button onClick={() => shiftMonth(-1)}>上一月</Button>
            <Button onClick={() => shiftMonth(1)}>下一月</Button>
          </Space>
        </div>
        {loading ? (
          <div className="note-calendar-loading">
            <Spin />
          </div>
        ) : (
          <div className="note-calendar-grid">
            {weekdayLabels.map((label) => (
              <div className="note-weekday" key={label}>
                {label}
              </div>
            ))}
            {cells.map((cell) => {
              const key = toDateKey(cell);
              const day = dayMap.get(key);
              const isCurrentMonth = cell.getMonth() === viewDate.getMonth();
              return (
                <Popover key={key} content={notePreview(day)} trigger="hover" placement="top">
                  <button
                    className={[
                      "note-day",
                      `note-day-level-${day?.detail_level || 0}`,
                      isCurrentMonth ? "" : "note-day-muted",
                      key === selectedDate ? "note-day-selected" : "",
                    ].join(" ")}
                    onClick={() => setSelectedDate(key)}
                  >
                    <span>{cell.getDate()}</span>
                    {day ? <small>{day.note_count} note</small> : null}
                  </button>
                </Popover>
              );
            })}
          </div>
        )}
      </section>

      <section className="glass-card note-detail-page">
        <div className="note-detail-head">
          <div>
            <Typography.Text className="eyebrow">Selected date</Typography.Text>
            <Typography.Title level={3}>{selectedDate}</Typography.Title>
          </div>
          {dailyResult?.optimized_file ? <Tag color="green">日报已保存</Tag> : null}
        </div>
        {!selectedDay ? (
          <Empty description="这一天还没有便条，先在上方写一条。" />
        ) : (
          <div className="note-edit-list">
            {selectedDay.notes.map((note) => (
              <div className="note-edit-item" key={note.id}>
                <Space className="note-edit-meta" wrap>
                  <Tag color="green">{periodLabels[note.period] || note.period}</Tag>
                  <Typography.Text type="secondary">
                    {note.updated_at.replace("T", " ")} · 详细度 {note.detail_level}
                  </Typography.Text>
                </Space>
                <Input.TextArea
                  rows={4}
                  value={editing[note.id] ?? note.content}
                  onChange={(event) => setEditing((current) => ({ ...current, [note.id]: event.target.value }))}
                />
                <Space wrap>
                  <Button type="primary" onClick={() => saveExisting(note)}>
                    修改
                  </Button>
                  <Button danger onClick={() => removeNote(note)}>
                    删除
                  </Button>
                </Space>
              </div>
            ))}
          </div>
        )}
      </section>
      <FloatingErrorButton
        errors={errorEntries}
        open={errorPopoverOpen}
        onOpenChange={setErrorPopoverOpen}
        onClear={() => {
          setErrorEntries([]);
          setErrorPopoverOpen(false);
        }}
      />
    </div>
  );
}
