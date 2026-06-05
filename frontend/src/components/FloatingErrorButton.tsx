import { Badge, Button, Popover } from "antd";
import { ExclamationCircleFilled } from "@ant-design/icons";

export type FloatingErrorEntry = {
  id: string;
  message: string;
  createdAt: string;
};

type Props = {
  errors: FloatingErrorEntry[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClear: () => void;
};

export function createFloatingErrorEntry(errorMessage: string): FloatingErrorEntry {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    message: errorMessage,
    createdAt: new Date().toLocaleString("zh-CN", { hour12: false }),
  };
}

export function FloatingErrorButton({ errors, open, onOpenChange, onClear }: Props) {
  if (!errors.length) {
    return null;
  }

  return (
    <Popover
      trigger="click"
      placement="leftBottom"
      open={open}
      onOpenChange={onOpenChange}
      overlayClassName="error-float-popover"
      content={(
        <div className="error-float-panel">
          <div className="error-float-header">
            <span>最近错误</span>
            <Button type="link" size="small" onClick={onClear}>
              清空
            </Button>
          </div>
          <div className="error-float-list">
            {errors.map((entry) => (
              <div key={entry.id} className="error-float-item">
                <div className="error-float-time">{entry.createdAt}</div>
                <div className="error-float-message">{entry.message}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    >
      <div className="error-float-wrap">
        <Badge count={errors.length} size="small">
          <button type="button" className="error-float-button" aria-label="查看最近错误">
            <ExclamationCircleFilled />
          </button>
        </Badge>
      </div>
    </Popover>
  );
}
