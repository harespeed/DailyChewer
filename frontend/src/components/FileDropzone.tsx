import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Form, Input, Upload, message } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import {
  fetchOptimizeIngestTask,
  optimizeIngestPreview,
  previewIngest,
  saveIngest,
  type IngestOptimizeTaskResponse,
  type IngestPreviewResponse,
} from "../api/client";
import { FloatingErrorButton, createFloatingErrorEntry, type FloatingErrorEntry } from "./FloatingErrorButton";
import { ReportPreview } from "./ReportPreview";

type Props = {
  onSaved: () => void;
};

type QuestionTrackItem = {
  id: string;
  lane: number;
  question: string;
  phase: "stable" | "enter-left" | "exit-right";
};

const MAX_QUESTION_LANES = 2;
const TRACK_EXIT_DURATION_MS = 360;

function buildQuestionTrack(question: string, lane: number, phase: QuestionTrackItem["phase"]): QuestionTrackItem {
  return {
    id: `${question}-${lane}-${Date.now()}`,
    lane,
    question,
    phase,
  };
}

function getIngestErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.includes("LLM 调用失败")) {
    return `${detail} 系统已对瞬时断连自动重试；如果仍然失败，请稍后重试或检查 LLM 配置与网络。`;
  }
  return detail || fallback;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isPreviewResponse(payload: unknown): payload is IngestPreviewResponse {
  return !!payload && typeof payload === "object" && "daily_report" in payload && "questions" in payload;
}

function isTaskResponse(payload: unknown): payload is IngestOptimizeTaskResponse {
  return !!payload && typeof payload === "object" && "task_id" in payload && "status" in payload;
}

export function FileDropzone({ onSaved }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<IngestPreviewResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [previewLoading, setPreviewLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [questionTracks, setQuestionTracks] = useState<QuestionTrackItem[]>([]);
  const [optimizingQuestions, setOptimizingQuestions] = useState<Record<string, boolean>>({});
  const [errorEntries, setErrorEntries] = useState<FloatingErrorEntry[]>([]);
  const [errorPopoverOpen, setErrorPopoverOpen] = useState(false);
  const [form] = Form.useForm();
  const trackTimerIdsRef = useRef<number[]>([]);
  const optimizeRequestSequenceRef = useRef(0);
  const latestAppliedOptimizeSequenceRef = useRef(0);
  const activeUploadIdRef = useRef<string | null>(null);

  const hasOptimizingQuestion = Object.values(optimizingQuestions).some(Boolean);
  const sortedQuestionTracks = [...questionTracks].sort((left, right) => left.lane - right.lane);

  const clearTrackTimers = () => {
    trackTimerIdsRef.current.forEach((timerId) => window.clearTimeout(timerId));
    trackTimerIdsRef.current = [];
  };

  const pushErrorEntry = (errorMessage: string) => {
    const entry = createFloatingErrorEntry(errorMessage);
    setErrorEntries((current) => [entry, ...current].slice(0, 20));
  };

  const notifyError = (errorMessage: string, messageKey?: string) => {
    pushErrorEntry(errorMessage);
    if (messageKey) {
      message.error({ content: errorMessage, key: messageKey });
      return;
    }
    message.error(errorMessage);
  };

  const resetQuestionState = () => {
    clearTrackTimers();
    setQuestionTracks([]);
    setOptimizingQuestions({});
    optimizeRequestSequenceRef.current = 0;
    latestAppliedOptimizeSequenceRef.current = 0;
    activeUploadIdRef.current = null;
  };

  const scheduleTrackUpdate = (nextItems: QuestionTrackItem[]) => {
    trackTimerIdsRef.current.push(
      window.setTimeout(() => {
        setQuestionTracks(nextItems);
      }, TRACK_EXIT_DURATION_MS),
    );
  };

  const syncInitialQuestionTracks = (current: QuestionTrackItem[], nextQuestions: string[]) => {
    const activeItems = current.filter((item) => item.phase !== "exit-right");
    const keptItems = activeItems
      .filter((item) => nextQuestions.includes(item.question))
      .slice(0, MAX_QUESTION_LANES)
      .map((item) => ({ ...item, phase: "stable" as const }));
    const exitingItems = activeItems
      .filter((item) => !keptItems.some((kept) => kept.question === item.question))
      .map((item) => ({ ...item, phase: "exit-right" as const }));
    const availableLanes = Array.from({ length: MAX_QUESTION_LANES }, (_, lane) => lane).filter(
      (lane) => !keptItems.some((item) => item.lane === lane),
    );
    const enteringItems = nextQuestions
      .filter((question) => !keptItems.some((item) => item.question === question))
      .slice(0, availableLanes.length)
      .map((question, index) => buildQuestionTrack(question, availableLanes[index], "enter-left"));

    if (!exitingItems.length) {
      return [...keptItems, ...enteringItems];
    }

    scheduleTrackUpdate([...keptItems, ...enteringItems]);
    return [...keptItems, ...exitingItems];
  };

  const syncSingleQuestionTrack = (
    current: QuestionTrackItem[],
    nextQuestions: string[],
    replacedQuestion: string,
  ) => {
    const activeItems = current.filter((item) => item.phase !== "exit-right");
    const replacedItem = activeItems.find((item) => item.question === replacedQuestion);

    if (!replacedItem) {
      return syncInitialQuestionTracks(current, nextQuestions);
    }

    const stableItems = activeItems
      .filter((item) => item.question !== replacedQuestion)
      .slice(0, MAX_QUESTION_LANES - 1)
      .map((item) => ({ ...item, phase: "stable" as const }));
    const stableQuestions = new Set(stableItems.map((item) => item.question));
    const replacementQuestion = nextQuestions.find(
      (question) => question !== replacedQuestion && !stableQuestions.has(question),
    );

    if (!replacementQuestion && nextQuestions.includes(replacedQuestion)) {
      return activeItems.map((item) => ({ ...item, phase: "stable" as const }));
    }

    const nextItems: QuestionTrackItem[] = [...stableItems];
    if (replacementQuestion) {
      nextItems.push(buildQuestionTrack(replacementQuestion, replacedItem.lane, "enter-left"));
    }

    scheduleTrackUpdate(nextItems);
    return [...stableItems, { ...replacedItem, phase: "exit-right" as const }];
  };

  const syncQuestionTracks = (nextQuestions: string[], preferredExitQuestion?: string) => {
    clearTrackTimers();
    setQuestionTracks((current) => {
      if (preferredExitQuestion) {
        return syncSingleQuestionTrack(current, nextQuestions, preferredExitQuestion);
      }
      return syncInitialQuestionTracks(current, nextQuestions);
    });
  };

  const applyPreviewResult = (result: IngestPreviewResponse, preferredExitQuestion?: string) => {
    activeUploadIdRef.current = result.upload_id;
    setPreview(result);
    syncQuestionTracks(result.questions, preferredExitQuestion);
  };

  useEffect(() => () => clearTrackTimers(), []);

  const handlePreview = async () => {
    if (!file) {
      message.warning("请先选择一个日报文件。");
      return;
    }
    const values = form.getFieldsValue();
    const formData = new FormData();
    formData.append("file", file);
    if (values.date) formData.append("date", values.date);
    if (values.project) formData.append("project", values.project);
    (values.tags || "")
      .split(",")
      .map((item: string) => item.trim())
      .filter(Boolean)
      .forEach((tag: string) => formData.append("tags", tag));
    formData.append("no_questions", String(!!values.no_questions));
    setPreviewLoading(true);
    try {
      const result = await previewIngest(formData);
      applyPreviewResult(result);
      message.success("已生成优化预览。");
    } catch (error: any) {
      notifyError(getIngestErrorMessage(error, "日报预览失败。"));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleOptimizeQuestion = async (question: string) => {
    if (!preview) {
      message.warning("请先生成预览。");
      return;
    }
    const answer = (answers[question] || "").trim();
    if (!answer) {
      message.warning("请先填写这一条补充信息。");
      return;
    }
    const requestSequence = ++optimizeRequestSequenceRef.current;
    setOptimizingQuestions((current) => ({
      ...current,
      [question]: true,
    }));
    try {
      const values = form.getFieldsValue();
      const optimizeResponse = await optimizeIngestPreview({
        upload_id: preview.upload_id,
        date: values.date,
        user_answers: Object.fromEntries(
          Object.entries(answers).filter(([, value]) => value.trim()),
        ),
      });
      if (isPreviewResponse(optimizeResponse)) {
        if (requestSequence >= latestAppliedOptimizeSequenceRef.current) {
          latestAppliedOptimizeSequenceRef.current = requestSequence;
          applyPreviewResult(optimizeResponse, question);
          message.success({ content: "预览已根据补充信息更新。", key: `optimize-${question}` });
        }
        return;
      }
      if (!isTaskResponse(optimizeResponse)) {
        notifyError("补充优化返回了无法识别的响应格式。", `optimize-${question}`);
        return;
      }
      message.loading({ content: "追问优化任务已入队，正在处理中…", key: `optimize-${question}` });
      for (let attempt = 0; attempt < 45; attempt += 1) {
        const latestTask = await fetchOptimizeIngestTask(optimizeResponse.task_id);
        if (latestTask.upload_id !== activeUploadIdRef.current) {
          return;
        }
        if (latestTask.status === "completed" && latestTask.result) {
          if (requestSequence >= latestAppliedOptimizeSequenceRef.current) {
            latestAppliedOptimizeSequenceRef.current = requestSequence;
            applyPreviewResult(latestTask.result, question);
            message.success({ content: "预览已根据补充信息更新。", key: `optimize-${question}` });
          }
          return;
        }
        if (latestTask.status === "failed") {
          notifyError(latestTask.error_message || "补充优化失败。", `optimize-${question}`);
          return;
        }
        await sleep(1200);
      }
      notifyError("追问优化任务等待超时，请重试。", `optimize-${question}`);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      if (detail === "Not Found") {
        notifyError("后端未提供追问任务状态接口。请重启后端，或让前后端代码版本保持一致。");
        return;
      }
      notifyError(getIngestErrorMessage(error, "补充优化失败。"));
    } finally {
      setOptimizingQuestions((current) => ({
        ...current,
        [question]: false,
      }));
    }
  };

  const handleSave = async () => {
    if (!preview) {
      message.warning("请先生成预览。");
      return;
    }
    const values = form.getFieldsValue();
    setSaveLoading(true);
    try {
      await saveIngest({
        upload_id: preview.upload_id,
        date: values.date,
        project: values.project,
        tags: (values.tags || "")
          .split(",")
          .map((item: string) => item.trim())
          .filter(Boolean),
        user_answers: answers,
      });
      message.success("日报已保存。");
      setPreview(null);
      setAnswers({});
      resetQuestionState();
      form.resetFields();
      setFile(null);
      onSaved();
    } catch (error: any) {
      notifyError(getIngestErrorMessage(error, "日报保存失败。"));
    } finally {
      setSaveLoading(false);
    }
  };

  return (
    <div className="stack">
      <Card className="glass-card" title="上传日报">
        <Form layout="vertical" form={form}>
          <Form.Item>
            <Upload.Dragger
              accept=".csv,.xlsx,.md,.markdown,.docx"
              beforeUpload={(nextFile) => {
                setFile(nextFile);
                setPreview(null);
                setAnswers({});
                resetQuestionState();
                return false;
              }}
              maxCount={1}
              onRemove={() => {
                setFile(null);
                setPreview(null);
                setAnswers({});
                resetQuestionState();
              }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击选择日报，或直接拖拽文件到这里</p>
              <p className="ant-upload-hint">支持 csv / xlsx / md / markdown / docx</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item name="date" label="日期">
            <Input placeholder="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="project" label="项目">
            <Input placeholder="例如 AI-App" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Input placeholder="使用逗号分隔，例如 automation,api" />
          </Form.Item>
          <Form.Item name="no_questions" valuePropName="checked">
            <Checkbox>跳过追问，直接生成保守版本</Checkbox>
          </Form.Item>
          <Button type="primary" onClick={handlePreview} loading={previewLoading} disabled={saveLoading || hasOptimizingQuestion}>
            Preview & Optimize
          </Button>
        </Form>
      </Card>

      <ReportPreview report={preview?.daily_report ?? null} qualityScore={preview?.quality_score ?? null} />

      {sortedQuestionTracks.length ? (
        <Card className="glass-card" title="需要补充的信息">
          <Alert type="info" showIcon message="补充任一条信息后都可以立即重新优化，预览会保留并继续追问缺失项。" />
          <div className="question-tracks">
            {sortedQuestionTracks.map((track) => (
              <div key={track.id} className="question-track">
                <div className={`question-card question-card-${track.phase}`}>
                  <div className="question-label">{track.question}</div>
                  <div className="question-actions">
                    <Input.TextArea
                      autoSize={{ minRows: 2, maxRows: 5 }}
                      value={answers[track.question] || ""}
                      placeholder="填写这一条补充信息，然后点击 Optimize"
                      onChange={(event) =>
                        setAnswers((current) => ({
                          ...current,
                          [track.question]: event.target.value,
                        }))
                      }
                    />
                    <Button
                      type="primary"
                      onClick={() => void handleOptimizeQuestion(track.question)}
                      loading={!!optimizingQuestions[track.question]}
                      disabled={saveLoading || previewLoading}
                    >
                      Optimize
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {preview ? (
        <Button
          type="primary"
          size="large"
          onClick={handleSave}
          loading={saveLoading}
          disabled={previewLoading || hasOptimizingQuestion}
        >
          Save Report
        </Button>
      ) : null}

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
