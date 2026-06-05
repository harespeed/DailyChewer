import axios from "axios";

const TOKEN_STORAGE_KEY = "dailychewer_access_token";

export interface ReportSection {
  work_content: string[];
  personal_growth: string[];
  problems: string[];
  solutions: string[];
}

export interface QualityScore {
  work_clarity: number;
  progress_clarity: number;
  problem_completeness: number;
  solution_clarity: number;
  growth_reflection: number;
  total: number;
  comments: string[];
}

export interface DailyReport {
  date: string;
  weekday: string;
  week: string;
  morning: ReportSection;
  afternoon: ReportSection;
  questions: string[];
  quality_score?: QualityScore | null;
}

export interface DoctorCheckItem {
  name: string;
  status: string;
  value: string;
  details: string;
}

export interface SearchResult {
  date: string;
  weekday: string;
  week: string;
  project?: string | null;
  tags: string[];
  matched_section: string;
  snippet: string;
  optimized_file: string;
}

export interface ReportIndexItem {
  date: string;
  weekday: string;
  week: string;
  project?: string | null;
  tags: string[];
  quality_score?: number | null;
  source_format: string;
  status: string;
  optimized_file: string;
}

export interface IngestPreviewResponse {
  upload_id: string;
  daily_report: DailyReport;
  questions: string[];
  quality_score?: QualityScore | null;
}

export interface IngestOptimizeTaskResponse {
  task_id: string;
  upload_id: string;
  sequence: number;
  status: "pending" | "running" | "completed" | "failed" | "superseded";
  result?: IngestPreviewResponse | null;
  error_message?: string | null;
}

export type OptimizeIngestResponse = IngestPreviewResponse | IngestOptimizeTaskResponse;

export interface DailyNote {
  id: string;
  date: string;
  weekday: string;
  period: "morning" | "afternoon" | string;
  content: string;
  detail_level: number;
  created_at: string;
  updated_at: string;
}

export interface DailyNoteDay {
  date: string;
  weekday: string;
  note_count: number;
  detail_level: number;
  preview: string;
  notes: DailyNote[];
}

export interface DailyNotesResponse {
  notes: DailyNote[];
  days: DailyNoteDay[];
}

export interface UserRead {
  id: string;
  username: string;
  display_name?: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserRead;
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.dispatchEvent(new CustomEvent("dailychewer:unauthorized", { detail: { message: "Session expired, please log in again." } }));
    }
    return Promise.reject(error);
  },
);

export function saveAccessToken(token: string) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearAccessToken() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function getAccessToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export async function login(payload: { username: string; password: string }) {
  const response = await api.post<TokenResponse>("/api/auth/login", payload);
  return response.data;
}

export async function register(payload: {
  username: string;
  password: string;
  display_name?: string;
}) {
  const response = await api.post<UserRead>("/api/auth/register", payload);
  return response.data;
}

export async function fetchMe() {
  const response = await api.get<UserRead>("/api/auth/me");
  return response.data;
}

export async function changePassword(payload: { old_password: string; new_password: string }) {
  const response = await api.post<{ status: string }>("/api/auth/change-password", payload);
  return response.data;
}

export async function fetchUsers() {
  const response = await api.get<UserRead[]>("/api/users");
  return response.data;
}

export async function updateUserStatus(userId: string, isActive: boolean) {
  const response = await api.patch<UserRead>(`/api/users/${userId}/status`, { is_active: isActive });
  return response.data;
}

export async function fetchDoctor(checkApi = false) {
  const response = await api.get<{ checks: DoctorCheckItem[] }>("/api/doctor", {
    params: { check_api: checkApi },
  });
  return response.data;
}

export async function previewIngest(formData: FormData) {
  const response = await api.post<IngestPreviewResponse>("/api/ingest/preview", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function optimizeIngestPreview(payload: {
  upload_id: string;
  date?: string;
  user_answers?: Record<string, string>;
}) {
  const response = await api.post<OptimizeIngestResponse>("/api/ingest/optimize", payload);
  return response.data;
}

export async function fetchOptimizeIngestTask(taskId: string) {
  const response = await api.get<IngestOptimizeTaskResponse>(`/api/ingest/optimize-tasks/${taskId}`);
  return response.data;
}

export async function saveIngest(payload: {
  upload_id: string;
  date?: string;
  project?: string;
  tags?: string[];
  user_answers?: Record<string, string>;
}) {
  const response = await api.post("/api/ingest/save", payload);
  return response.data;
}

export async function fetchReports(params: { week?: string; project?: string; tag?: string }) {
  const response = await api.get<ReportIndexItem[]>("/api/reports", { params });
  return response.data;
}

export async function searchReports(params: {
  q: string;
  week?: string;
  from_date?: string;
  to_date?: string;
  project?: string;
  tag?: string;
  limit?: number;
}) {
  const response = await api.get<SearchResult[]>("/api/search", { params });
  return response.data;
}

export async function fetchDailyNotes(month: string) {
  const response = await api.get<DailyNotesResponse>("/api/notes", { params: { month } });
  return response.data;
}

export async function fetchDailyNotesForDate(date: string) {
  const response = await api.get<DailyNotesResponse>(`/api/notes/${date}`);
  return response.data;
}

export async function createDailyNote(payload: { content: string; date?: string; period?: string }) {
  const response = await api.post<DailyNote>("/api/notes", payload);
  return response.data;
}

export async function updateDailyNote(noteId: string, payload: { content: string; period?: string }) {
  const response = await api.patch<DailyNote>(`/api/notes/${noteId}`, payload);
  return response.data;
}

export async function deleteDailyNote(noteId: string) {
  const response = await api.delete<{ deleted: boolean }>(`/api/notes/${noteId}`);
  return response.data;
}

export async function generateDailyFromNotes(date: string) {
  const response = await api.post<{
    saved: boolean;
    raw_file?: string | null;
    optimized_file?: string | null;
    index_item?: ReportIndexItem | null;
  }>(`/api/notes/${date}/generate-daily`);
  return response.data;
}

export async function generateWeeklyFromNotes(date: string) {
  const response = await api.post<{ file?: string; file_id?: string; preview: string; download_url?: string | null }>(
    `/api/notes/${date}/generate-weekly`,
  );
  return response.data;
}

export async function generateWeeklyRangeFromNotes(payload: { from_date: string; to_date: string }) {
  const response = await api.post<{ file?: string; file_id?: string; preview: string; download_url?: string | null }>(
    "/api/notes/generate-weekly-range",
    payload,
  );
  return response.data;
}

export async function generateWeekly(payload: {
  week?: string;
  from_date?: string;
  to_date?: string;
  format: string;
  style: string;
  project?: string;
  tags?: string[];
  save: boolean;
}) {
  const response = await api.post("/api/weekly", payload);
  return response.data as { file?: string; preview: string; download_url?: string | null };
}

export async function generateMonthly(payload: {
  month: string;
  format: string;
  style: string;
  project?: string;
  tags?: string[];
  save: boolean;
}) {
  const response = await api.post("/api/monthly", payload);
  return response.data as { file?: string; preview: string; download_url?: string | null };
}

export async function generateTemplate(payload: { date?: string; format: string }) {
  const response = await api.post("/api/template", payload);
  return response.data as { file: string; download_url?: string | null };
}

export async function downloadProtectedFile(downloadUrl: string, fallbackName?: string) {
  const response = await api.get(downloadUrl, { responseType: "blob" });
  const blobUrl = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download =
    fallbackName ||
    response.headers["content-disposition"]?.match(/filename="?([^"]+)"?/)?.[1] ||
    "dailychewer-download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}
