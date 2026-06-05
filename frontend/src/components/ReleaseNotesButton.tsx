import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Popover, Typography } from "antd";
import { NotificationOutlined } from "@ant-design/icons";
import { releaseNotes } from "../releaseNotes";

const RELEASE_NOTES_SEEN_KEY = "dailychewer_release_notes_seen_id";

function noteId(note: { timestamp: string; title: string }) {
  return `${note.timestamp}-${note.title}`;
}

function ReleaseNotesContent({
  onViewedAll,
}: {
  onViewedAll: () => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  const checkViewedAll = () => {
    const panel = panelRef.current;
    if (!panel) return;
    const reachedBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 8;
    if (reachedBottom) {
      onViewedAll();
    }
  };

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      const panel = panelRef.current;
      if (!panel) return;
      if (panel.scrollHeight <= panel.clientHeight + 8) {
        onViewedAll();
      }
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [onViewedAll]);

  return (
    <div
      ref={panelRef}
      className="release-notes-panel"
      onScroll={checkViewedAll}
    >
      {releaseNotes.map((note) => (
        <div key={`${note.timestamp}-${note.title}`} className="release-note-entry">
          <Typography.Text className="release-note-date">{note.timestamp}</Typography.Text>
          <Typography.Title level={5}>{note.title}</Typography.Title>
          <ul className="release-note-list">
            {note.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function ReleaseNotesButton() {
  const latestNoteId = useMemo(
    () => (releaseNotes.length ? noteId(releaseNotes[0]) : null),
    [],
  );
  const [open, setOpen] = useState(false);
  const [seenLatestId, setSeenLatestId] = useState<string | null>(() => localStorage.getItem(RELEASE_NOTES_SEEN_KEY));

  const unseenCount = useMemo(() => {
    if (!releaseNotes.length) return 0;
    if (!seenLatestId) return releaseNotes.length;
    const seenIndex = releaseNotes.findIndex((note) => noteId(note) === seenLatestId);
    if (seenIndex === -1) return releaseNotes.length;
    return Math.max(0, seenIndex);
  }, [seenLatestId]);

  const markAllViewed = () => {
    if (!latestNoteId) return;
    localStorage.setItem(RELEASE_NOTES_SEEN_KEY, latestNoteId);
    setSeenLatestId(latestNoteId);
  };

  return (
    <Popover
      placement="bottomRight"
      trigger="hover"
      open={open}
      onOpenChange={setOpen}
      mouseEnterDelay={0.12}
      mouseLeaveDelay={0.18}
      overlayClassName="release-notes-popover"
      content={<ReleaseNotesContent onViewedAll={markAllViewed} />}
    >
      <Badge count={unseenCount} size="small">
        <Button icon={<NotificationOutlined />} className="release-notes-button">
          更新日志
        </Button>
      </Badge>
    </Popover>
  );
}
