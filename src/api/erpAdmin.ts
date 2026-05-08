import { axiosClient } from "@/api/axiosClient";

export interface AdminSessionDto {
  session_id: string;
  user: { id: string; email: string; name?: string; role?: string };
  permissions: string[];
}

export interface ERPConfigDto {
  db_type: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
  password_masked: string;
  enabled: boolean;
  updated_at: string;
  updated_by_user_id: string;
}

export interface ERPConfigUpsertPayload {
  db_type: string;
  host: string;
  port: number;
  db_name: string;
  username: string;
  password: string;
  enabled: boolean;
}

export interface ERPConnectionTestDto {
  ok: boolean;
  detail: string;
}

export interface AdminMonitoringOverviewDto {
  app_uptime_seconds: number;
  users_count: number;
  short_memories_count: number;
  long_memories_count: number;
  classification_jobs_total: number;
  classification_jobs_running: number;
  classification_jobs_done: number;
  classification_jobs_error: number;
  request_type_counts: Record<string, number>;
  recent_executions: Array<{
    updated_at: string;
    memory_key: string;
    route_intent: string;
    article_id: string;
    session_id: string;
    response_excerpt: string;
  }>;
  instance_performance: Record<string, number>;
  subagent_traces: Array<{
    trace_time: string;
    subagent: string;
    status: string;
    details: string;
  }>;
}

export interface AdminBootstrapPayload {
  email: string;
  bootstrap_key: string;
}

export interface SelfLearningJobDto {
  job_id: string;
  status: string;
  detail: string;
  target_model: string;
  dataset_path: string;
  output_path: string;
  memories_used: number;
  started_at: string;
  updated_at: string;
}

export interface WarehouseIngestionJobDto {
  job_id: string;
  filename: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  progress_pct: number;
  counts: Record<string, number>;
  qty_by_label_kg?: Record<string, number>;
  cancel_requested?: boolean;
  error: string;
  batch_id: string;
}

export interface WarehouseSummaryDto {
  total_records: number;
  latest_batch_id: string;
  latest_source_file: string;
  latest_snapshot_date: string;
  total_stock_kg: number;
  labels: Record<string, number>;
  qty_by_label_kg?: Record<string, number>;
  top_ingredients_kg?: Array<{
    ingredient: string;
    label: string;
    qty_kg: number;
  }>;
}

export async function getAdminSession(): Promise<AdminSessionDto> {
  const { data } = await axiosClient.get<AdminSessionDto>("/auth/admin/session");
  return data;
}

export async function getERPConfig(): Promise<ERPConfigDto> {
  const { data } = await axiosClient.get<ERPConfigDto>("/erp/admin/config");
  return data;
}

export async function saveERPConfig(payload: ERPConfigUpsertPayload): Promise<ERPConfigDto> {
  const { data } = await axiosClient.post<ERPConfigDto>("/erp/admin/config", payload);
  return data;
}

export async function testERPConnection(): Promise<ERPConnectionTestDto> {
  const { data } = await axiosClient.post<ERPConnectionTestDto>("/erp/admin/test-connection");
  return data;
}

export async function getAdminMonitoringOverview(): Promise<AdminMonitoringOverviewDto> {
  const { data } = await axiosClient.get<AdminMonitoringOverviewDto>("/admin/monitoring/overview");
  return data;
}

export async function bootstrapAdminRole(payload: AdminBootstrapPayload): Promise<void> {
  await axiosClient.post("/auth/admin/bootstrap", payload);
}

export async function startSelfLearningRetrain(payload: {
  target_model: string;
  max_memories: number;
}): Promise<SelfLearningJobDto> {
  const { data } = await axiosClient.post<SelfLearningJobDto>("/admin/self-learning/retrain", payload);
  return data;
}

export async function getSelfLearningJob(jobId: string): Promise<SelfLearningJobDto> {
  const { data } = await axiosClient.get<SelfLearningJobDto>(`/admin/self-learning/job/${jobId}`);
  return data;
}

export async function uploadWarehouseExtract(file: File, categorieDefault = ""): Promise<WarehouseIngestionJobDto> {
  const form = new FormData();
  form.append("file", file);
  form.append("categorie_default", categorieDefault);
  const { data } = await axiosClient.post<WarehouseIngestionJobDto>("/admin/warehouse/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 60 * 60 * 1000,
  });
  return data;
}

export async function getWarehouseIngestionJob(jobId: string): Promise<WarehouseIngestionJobDto> {
  const { data } = await axiosClient.get<WarehouseIngestionJobDto>(`/admin/warehouse/upload/${jobId}`);
  return data;
}

export async function cancelWarehouseIngestionJob(jobId: string): Promise<WarehouseIngestionJobDto> {
  const { data } = await axiosClient.post<WarehouseIngestionJobDto>(`/admin/warehouse/upload/${jobId}/cancel`);
  return data;
}

export async function getWarehouseSummary(): Promise<WarehouseSummaryDto> {
  const { data } = await axiosClient.get<WarehouseSummaryDto>("/admin/warehouse/summary");
  return data;
}

export async function exportWarehouseCsv(): Promise<Blob> {
  const { data } = await axiosClient.get("/admin/warehouse/export.csv", {
    responseType: "blob",
  });
  return data as Blob;
}
