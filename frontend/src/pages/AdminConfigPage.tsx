import { useEffect, useRef, useState } from "react";
import { Database, ShieldCheck, Wifi } from "lucide-react";
import {
  bootstrapAdminRole,
  cancelWarehouseIngestionJob,
  exportWarehouseCsv,
  getWarehouseIngestionJob,
  getWarehouseSummary,
  getAdminSession,
  getERPConfig,
  saveERPConfig,
  testERPConnection,
  uploadWarehouseExtract,
  type ERPConfigUpsertPayload,
  type WarehouseIngestionJobDto,
  type WarehouseSummaryDto,
} from "@/api/erpAdmin";

const DB_TYPES = ["postgresql", "mysql", "sqlserver", "sqlite"] as const;
const WAREHOUSE_LIVE_SUMMARY_KEY = "sotipapier_warehouse_live_summary";
const WAREHOUSE_ACTIVE_JOB_KEY = "sotipapier_warehouse_active_job_id";

export function AdminConfigPage() {
  const warehouseFileInputRef = useRef<HTMLInputElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [adminSessionId, setAdminSessionId] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [bootstrapKey, setBootstrapKey] = useState("");
  const [promoting, setPromoting] = useState(false);
  const [warehouseFile, setWarehouseFile] = useState<File | null>(null);
  const [warehouseUploading, setWarehouseUploading] = useState(false);
  const [warehouseJob, setWarehouseJob] = useState<WarehouseIngestionJobDto | null>(null);
  const [warehouseSummary, setWarehouseSummary] = useState<WarehouseSummaryDto | null>(null);
  const [form, setForm] = useState<ERPConfigUpsertPayload>({
    db_type: "postgresql",
    host: "",
    port: 5432,
    db_name: "",
    username: "",
    password: "",
    enabled: false,
  });

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [session, cfg, wh] = await Promise.all([getAdminSession(), getERPConfig(), getWarehouseSummary()]);
        if (!active) return;
        setAdminSessionId(session.session_id);
        setForm((prev) => ({
          ...prev,
          db_type: cfg.db_type || "postgresql",
          host: cfg.host || "",
          port: cfg.port || 5432,
          db_name: cfg.db_name || "",
          username: cfg.username || "",
          password: "",
          enabled: Boolean(cfg.enabled),
        }));
        setWarehouseSummary(wh);
        // Reset process cache on page load: start from fresh state.
        setWarehouseJob(null);
      } catch (e: unknown) {
        const msg = e && typeof e === "object" && "message" in e ? String((e as { message?: string }).message) : "Erreur admin.";
        if (active) setMessage(msg);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!warehouseJob?.job_id) return;
    if (!["queued", "running"].includes(String(warehouseJob.status || "").toLowerCase())) return;
    const t = setInterval(async () => {
      try {
        const next = await getWarehouseIngestionJob(warehouseJob.job_id);
        setWarehouseJob(next);
        const wh = await getWarehouseSummary();
        setWarehouseSummary(wh);
        // IMPORTANT: publish one merged live payload to avoid overriding qty_by_label_kg with an empty summary.
        const mergedQty = Object.keys(next.qty_by_label_kg || {}).length
          ? next.qty_by_label_kg
          : wh.qty_by_label_kg || {};
        try {
          localStorage.setItem(
            WAREHOUSE_LIVE_SUMMARY_KEY,
            JSON.stringify({
              at: new Date().toISOString(),
              summary: {
                ...wh,
                qty_by_label_kg: mergedQty,
              },
            })
          );
          window.dispatchEvent(new Event("sotipapier:warehouse-summary-updated"));
        } catch {
          // ignore localStorage/runtime issues
        }
        const status = String(next.status || "").toLowerCase();
        if (["done", "cancelled", "error"].includes(status)) {
          try {
            localStorage.removeItem(WAREHOUSE_ACTIVE_JOB_KEY);
            window.dispatchEvent(new Event("sotipapier:warehouse-job-updated"));
          } catch {
            // ignore localStorage/runtime issues
          }
          if (status === "done") setMessage("Base magasin construite depuis l'extrait réel.");
          if (status === "cancelled") setMessage("Processus arrêté par opérateur.");
          if (status === "error") setMessage(`Erreur process: ${next.error || "inconnue"}`);
        }
      } catch {
        // keep polling
      }
    }, 2000);
    return () => clearInterval(t);
  }, [warehouseJob?.job_id, warehouseJob?.status]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const saved = await saveERPConfig(form);
      setMessage(`Configuration ERP enregistrée (${saved.db_type}@${saved.host}:${saved.port}).`);
      setForm((prev) => ({ ...prev, password: "" }));
    } catch (e: unknown) {
      const msg = e && typeof e === "object" && "message" in e ? String((e as { message?: string }).message) : "Sauvegarde impossible.";
      setMessage(msg);
    } finally {
      setSaving(false);
    }
  }

  async function handleTestConnection() {
    setTesting(true);
    setMessage("");
    try {
      const res = await testERPConnection();
      setMessage(res.ok ? `Test ERP OK: ${res.detail}` : `Test ERP KO: ${res.detail}`);
    } catch (e: unknown) {
      const msg = e && typeof e === "object" && "message" in e ? String((e as { message?: string }).message) : "Test connexion impossible.";
      setMessage(msg);
    } finally {
      setTesting(false);
    }
  }

  async function handlePromoteAdmin(e: React.FormEvent) {
    e.preventDefault();
    setPromoting(true);
    setMessage("");
    try {
      await bootstrapAdminRole({ email: adminEmail.trim(), bootstrap_key: bootstrapKey });
      setMessage("Configuration admin appliquée: utilisateur promu admin.");
      setBootstrapKey("");
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message?: string }).message)
          : "Promotion admin impossible.";
      setMessage(msg);
    } finally {
      setPromoting(false);
    }
  }

  async function handleUploadWarehouseExtract() {
    if (!warehouseFile || warehouseUploading) return;
    setWarehouseUploading(true);
    setMessage("");
    try {
      const created = await uploadWarehouseExtract(warehouseFile, form.db_name || "");
      setWarehouseJob(created);
      try {
        localStorage.setItem(WAREHOUSE_ACTIVE_JOB_KEY, created.job_id);
        window.dispatchEvent(new Event("sotipapier:warehouse-job-updated"));
      } catch {
        // ignore localStorage/runtime issues
      }
      setMessage("Upload lancé: classification PDR + CHIMIE et construction DB magasin en cours.");
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message?: string }).message)
          : "Upload magasin impossible.";
      setMessage(msg);
    } finally {
      setWarehouseUploading(false);
    }
  }

  async function handleExportWarehouseCsv() {
    setMessage("");
    try {
      const blob = await exportWarehouseCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `warehouse_classified_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessage("Export CSV téléchargé.");
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message?: string }).message)
          : "Export CSV impossible.";
      setMessage(msg);
    }
  }

  async function handleResetWarehouseProcess() {
    const currentJobId = warehouseJob?.job_id;
    const currentStatus = String(warehouseJob?.status || "").toLowerCase();
    if (currentJobId && ["queued", "running", "cancelling"].includes(currentStatus)) {
      try {
        await cancelWarehouseIngestionJob(currentJobId);
      } catch {
        // ignore cancel errors and continue local reset
      }
    }
    setWarehouseUploading(false);
    setWarehouseJob(null);
    setWarehouseFile(null);
    setWarehouseSummary(null);
    if (warehouseFileInputRef.current) {
      warehouseFileInputRef.current.value = "";
    }
    try {
      localStorage.removeItem(WAREHOUSE_ACTIVE_JOB_KEY);
      localStorage.removeItem(WAREHOUSE_LIVE_SUMMARY_KEY);
      window.dispatchEvent(new Event("sotipapier:warehouse-job-updated"));
      window.dispatchEvent(new Event("sotipapier:warehouse-summary-updated"));
    } catch {
      // ignore localStorage/runtime issues
    }
    setMessage("Processus upload/classification réinitialisé (cache local vidé).");
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
        <div className="mb-2 flex items-center gap-2 text-steel-300">
          <ShieldCheck className="h-5 w-5 text-plant-accent" />
          <h1 className="text-lg font-semibold">Session admin ERP</h1>
        </div>
        <p className="font-mono text-xs text-steel-500">
          Session active: {adminSessionId || "chargement..."}
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-3 rounded-sm border border-navy-700 bg-navy-950/70 p-4">
        <div className="mb-1 flex items-center gap-2 text-steel-300">
          <Database className="h-5 w-5 text-cyan-400" />
          <h2 className="text-base font-semibold">Configuration SQL ERP (read-only recommandé)</h2>
        </div>

        {loading ? <p className="text-sm text-steel-500">Chargement configuration...</p> : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-steel-500">
            Type SQL
            <select
              value={form.db_type}
              onChange={(e) => setForm((f) => ({ ...f, db_type: e.target.value }))}
              className="hmi-input mt-1 w-full text-sm"
            >
              {DB_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-steel-500">
            Host
            <input
              value={form.host}
              onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
          <label className="text-xs text-steel-500">
            Port
            <input
              type="number"
              value={form.port}
              onChange={(e) => setForm((f) => ({ ...f, port: Number(e.target.value || 0) }))}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
          <label className="text-xs text-steel-500">
            Database
            <input
              value={form.db_name}
              onChange={(e) => setForm((f) => ({ ...f, db_name: e.target.value }))}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
          <label className="text-xs text-steel-500">
            Username
            <input
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
          <label className="text-xs text-steel-500">
            Password (laisser vide pour conserver)
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
        </div>

        <label className="inline-flex items-center gap-2 text-xs text-steel-400">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
          />
          Activer la connexion ERP SQL
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={saving || loading}
            className="rounded-sm bg-cyan-600 px-3 py-2 text-xs font-semibold text-navy-950 disabled:opacity-40"
          >
            {saving ? "Enregistrement..." : "Enregistrer config"}
          </button>
          <button
            type="button"
            disabled={testing || loading}
            onClick={() => void handleTestConnection()}
            className="inline-flex items-center gap-1 rounded-sm border border-plant-accent/35 bg-plant-accent/10 px-3 py-2 text-xs font-semibold text-plant-glow disabled:opacity-40"
          >
            <Wifi className="h-3.5 w-3.5" />
            {testing ? "Test..." : "Tester connexion ERP"}
          </button>
        </div>

        {message ? (
          <p className="rounded-sm border border-navy-700 bg-navy-900/60 px-3 py-2 text-xs text-steel-300">{message}</p>
        ) : null}
      </form>

      <form onSubmit={handlePromoteAdmin} className="space-y-3 rounded-sm border border-navy-700 bg-navy-950/70 p-4">
        <div className="mb-1 flex items-center gap-2 text-steel-300">
          <ShieldCheck className="h-5 w-5 text-alert-orange" />
          <h2 className="text-base font-semibold">Configuration Admin</h2>
        </div>
        <p className="text-xs text-steel-500">
          Utiliser une seule fois pour promouvoir un compte en admin (bootstrap key).
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-steel-500">
            Email utilisateur
            <input
              type="email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
          <label className="text-xs text-steel-500">
            Bootstrap key
            <input
              type="password"
              value={bootstrapKey}
              onChange={(e) => setBootstrapKey(e.target.value)}
              className="hmi-input mt-1 w-full text-sm"
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={promoting || !adminEmail.trim() || !bootstrapKey.trim()}
          className="rounded-sm bg-alert-orange px-3 py-2 text-xs font-semibold text-navy-950 disabled:opacity-40"
        >
          {promoting ? "Configuration..." : "Configurer Admin"}
        </button>
      </form>

      <div className="space-y-3 rounded-sm border border-navy-700 bg-navy-950/70 p-4">
        <div className="mb-1 flex items-center gap-2 text-steel-300">
          <Database className="h-5 w-5 text-plant-accent" />
          <h2 className="text-base font-semibold">Upload extrait magasin (CSV/XLSX depuis 2017)</h2>
        </div>
        <p className="text-xs text-steel-500">
          Cette action active agent-pdr + agent-classification-chimie et reconstruit la base magasin réelle.
        </p>
        <p className="text-[11px] text-steel-600">
          Le job continue en arrière-plan même si vous changez de page; le suivi reprend automatiquement au retour.
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="hmi-input flex h-10 cursor-pointer items-center px-3 text-xs">
            <span className="truncate text-steel-400">
              {warehouseFile ? warehouseFile.name : "Choisir fichier CSV/XLSX magasin"}
            </span>
            <input
              ref={warehouseFileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={(e) => setWarehouseFile(e.target.files?.[0] || null)}
            />
          </label>
          <button
            type="button"
            onClick={() => void handleUploadWarehouseExtract()}
            disabled={!warehouseFile || warehouseUploading}
            className="rounded-sm bg-plant-accent px-3 py-2 text-xs font-semibold text-navy-950 disabled:opacity-40"
          >
            {warehouseUploading ? "Upload..." : "Uploader et construire la base"}
          </button>
          <button
            type="button"
            onClick={() => void handleExportWarehouseCsv()}
            disabled={!warehouseSummary?.total_records}
            className="rounded-sm border border-cyan-500/35 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-300 disabled:opacity-40"
          >
            Exporter la base classifiée (CSV)
          </button>
          <button
            type="button"
            onClick={() => void handleResetWarehouseProcess()}
            className="rounded-sm border border-alert-orange/50 bg-alert-orange/10 px-3 py-2 text-xs font-semibold text-alert-orange"
          >
            Réinitialiser process
          </button>
        </div>

        {warehouseJob ? (
          <div className="rounded-sm border border-navy-800 bg-navy-900/60 p-2 text-xs text-steel-400">
            <p>Job: {warehouseJob.job_id}</p>
            <p>Status: {warehouseJob.status}</p>
            <p>
              Progress: {warehouseJob.processed_rows}/{warehouseJob.total_rows} ({warehouseJob.progress_pct}%)
            </p>
            <p>
              MP={warehouseJob.counts.MP || 0} | PDR={warehouseJob.counts.PDR || 0} | CHIMIE=
              {warehouseJob.counts.CHIMIE || 0} | ERR={warehouseJob.counts.ERROR || 0}
            </p>
            {warehouseJob.error ? <p className="text-alert-red">Erreur: {warehouseJob.error}</p> : null}
          </div>
        ) : null}

        {warehouseSummary ? (
          <div className="rounded-sm border border-navy-800 bg-navy-900/60 p-2 text-xs text-steel-400">
            <p>Total records base magasin: {warehouseSummary.total_records}</p>
            <p>Total stock (kg): {Number(warehouseSummary.total_stock_kg || 0).toFixed(2)}</p>
            <p>Latest batch: {warehouseSummary.latest_batch_id || "N/A"}</p>
            <p>Source file: {warehouseSummary.latest_source_file || "N/A"}</p>
            <p>Date contexte extrait: {warehouseSummary.latest_snapshot_date || "N/A"}</p>
            <p>
              Labels:{" "}
              {Object.entries(warehouseSummary.labels || {})
                .map(([k, v]) => `${k}=${v}`)
                .join(" | ") || "N/A"}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
