export interface FileClassificationRow {
  id_article_erp: string;
  description: string;
  categorie: string;
  stage1_mp_pdr: string;
  stage2_mp_chimie: string;
  final_label: string;
  error: string;
}

export interface FileClassificationJobResponse {
  job_id: string;
  filename: string;
  status: "queued" | "running" | "done" | "error";
  total_rows: number;
  processed_rows: number;
  progress_pct: number;
  counts: Record<string, number>;
  error: string;
  recent_results: FileClassificationRow[];
}
