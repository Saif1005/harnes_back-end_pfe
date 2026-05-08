import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, Server } from "lucide-react";
import {
  getAdminMonitoringOverview,
  getSelfLearningJob,
  startSelfLearningRetrain,
  type AdminMonitoringOverviewDto,
  type SelfLearningJobDto,
} from "@/api/erpAdmin";

export function AdminMonitoringPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [slError, setSlError] = useState("");
  const [slLoading, setSlLoading] = useState(false);
  const [slJob, setSlJob] = useState<SelfLearningJobDto | null>(null);
  const [data, setData] = useState<AdminMonitoringOverviewDto | null>(null);

  const load = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const out = await getAdminMonitoringOverview();
      setData(out);
    } catch (e: unknown) {
      const msg = e && typeof e === "object" && "message" in e ? String((e as { message?: string }).message) : "Erreur monitoring.";
      setError(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => {
      void load(true);
    }, 10000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (!slJob?.job_id) return;
    if (!["queued", "running"].includes(String(slJob.status || "").toLowerCase())) return;
    const t = setInterval(async () => {
      try {
        const next = await getSelfLearningJob(slJob.job_id);
        setSlJob(next);
      } catch {
        // keep polling
      }
    }, 2000);
    return () => clearInterval(t);
  }, [slJob?.job_id, slJob?.status]);

  async function handleStartSelfLearning() {
    setSlLoading(true);
    setSlError("");
    try {
      const job = await startSelfLearningRetrain({
        target_model: "mistral:7b-instruct",
        max_memories: 500,
      });
      setSlJob(job);
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message?: string }).message)
          : "Impossible de lancer le self-learning.";
      setSlError(msg);
    } finally {
      setSlLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-steel-300">
            <Server className="h-5 w-5 text-cyan-400" />
            <h1 className="text-lg font-semibold">Monitoring background application</h1>
          </div>
          <button
            type="button"
            onClick={() => void load(true)}
            className="inline-flex items-center gap-1 rounded-sm border border-navy-700 px-2 py-1 text-[11px] text-steel-500 hover:bg-navy-900"
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
        <p className="mt-1 text-xs text-steel-500">Auto-refresh toutes les 10 secondes.</p>
      </div>

      {loading ? <p className="text-sm text-steel-500">Chargement monitoring...</p> : null}
      {error ? <p className="rounded-sm border border-alert-red/40 bg-alert-red/10 px-3 py-2 text-xs text-alert-red">{error}</p> : null}

      {data ? (
        <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-steel-300">
              Self-learning (db_long_memory -{"\u003e"} réentraînement cerveau Mistral)
            </h2>
            <button
              type="button"
              onClick={() => void handleStartSelfLearning()}
              disabled={slLoading || (slJob?.status === "running" || slJob?.status === "queued")}
              className="rounded-sm bg-plant-accent px-3 py-2 text-xs font-semibold text-navy-950 disabled:opacity-40"
            >
              {slLoading ? "Lancement..." : "Rentrainer modèle cerveau"}
            </button>
          </div>
          {slError ? (
            <p className="mt-2 rounded-sm border border-alert-red/40 bg-alert-red/10 px-3 py-2 text-xs text-alert-red">
              {slError}
            </p>
          ) : null}
          {slJob ? (
            <div className="mt-2 rounded-sm border border-navy-800 bg-navy-900/60 p-2 text-xs text-steel-400">
              <p>Job: {slJob.job_id}</p>
              <p>Status: {slJob.status}</p>
              <p>Detail: {slJob.detail}</p>
              <p>Memories utilisées: {slJob.memories_used}</p>
              <p>Dataset: {slJob.dataset_path || "N/A"}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Uptime (s)" value={String(data.app_uptime_seconds)} />
          <Stat label="Users" value={String(data.users_count)} />
          <Stat label="Short memory rows" value={String(data.short_memories_count)} />
          <Stat label="Long memory rows" value={String(data.long_memories_count)} />
          <Stat label="Jobs total" value={String(data.classification_jobs_total)} />
          <Stat label="Jobs running" value={String(data.classification_jobs_running)} />
          <Stat label="Jobs done" value={String(data.classification_jobs_done)} />
          <Stat label="Jobs error" value={String(data.classification_jobs_error)} tone="warn" />
        </div>
      ) : null}

      {data ? (
        <>
          <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
            <div className="mb-2 flex items-center gap-2 text-steel-300">
              <Activity className="h-4 w-4 text-plant-accent" />
              <h2 className="text-sm font-semibold">Type de requêtes</h2>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(data.request_type_counts || {}).map(([k, v]) => (
                <Stat key={k} label={k} value={String(v)} />
              ))}
            </div>
          </div>

          <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
            <h2 className="mb-2 text-sm font-semibold text-steel-300">Performance de l'instance</h2>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(data.instance_performance || {}).map(([k, v]) => (
                <Stat key={k} label={k} value={String(v)} />
              ))}
            </div>
          </div>

          <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
            <h2 className="mb-2 text-sm font-semibold text-steel-300">Execution récente</h2>
            <div className="hmi-scrollbar max-h-56 overflow-auto space-y-2">
              {data.recent_executions?.map((r) => (
                <div key={r.memory_key} className="rounded-sm border border-navy-800 bg-navy-900/60 p-2">
                  <p className="font-mono text-[10px] text-steel-500">
                    {r.updated_at} · {r.route_intent} · {r.article_id}
                  </p>
                  <p className="text-xs text-steel-300">{r.response_excerpt}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
            <h2 className="mb-2 text-sm font-semibold text-steel-300">Trace des sous-agents</h2>
            <div className="hmi-scrollbar max-h-56 overflow-auto space-y-2">
              {data.subagent_traces?.map((t, i) => (
                <div key={`${t.trace_time}-${i}`} className="rounded-sm border border-navy-800 bg-navy-900/60 p-2">
                  <p className="font-mono text-[10px] text-steel-500">
                    {t.trace_time} · {t.subagent} · {t.status}
                  </p>
                  <p className="text-xs text-steel-300">{t.details}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value, tone = "normal" }: { label: string; value: string; tone?: "normal" | "warn" }) {
  return (
    <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-3">
      <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${tone === "warn" ? "text-alert-orange" : "text-steel-200"}`}>{value}</p>
    </div>
  );
}
