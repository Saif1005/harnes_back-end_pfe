import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Layers, Package, TrendingUp } from "lucide-react";
import { getProductionDashboard } from "@/api/dashboard";
import { getWarehouseIngestionJob, getWarehouseSummary } from "@/api/erpAdmin";
import { HmiTag, IndustrialPanel } from "@/components/IndustrialPanel";
import type { AskAgentResponse } from "@/types/askAgent";
import type { ProductionDashboardResponse } from "@/types/dashboard";

const tooltipStyle = {
  backgroundColor: "#0a1628",
  border: "1px solid #153a5c",
  borderRadius: "2px",
  color: "#e5e7eb",
  fontSize: "12px",
};

const TREND_COLORS = ["#22d3ee", "#0ea5e9", "#ea580c", "#a3a3a3", "#10b981", "#f59e0b"];
const STOCK_HISTORY_KEY = "sotipapier_stock_class_history_v2";
const STOCK_HISTORY_LIMIT = 60;
const WAREHOUSE_LIVE_SUMMARY_KEY = "sotipapier_warehouse_live_summary";
const WAREHOUSE_ACTIVE_JOB_KEY = "sotipapier_warehouse_active_job_id";

const INGREDIENT_DISPLAY_MAP: Record<string, string> = {
  "waste paper ratio": "Vieux papier",
  "starch cationic ratio": "Amidon cationique",
  "starch oxidized ratio": "Amidon oxyde",
  "biocide ratio": "Biocide",
  "defoamer ratio (defoamer 1 (afranil))": "Antimousse afranil",
  "retention aids ratio": "Agent de retention",
  "krofta polymer ratio": "Polymere krofta",
  "prestige cleaning aids ratio (prestige)": "Prestige",
  "pulp ratio": "Pate papier",
  "standard pulp ratio": "Pate standard",
  "flocon pulp ratio": "Pate flocon",
  "sizing kraft (agent collage asa)": "Agent collage ASA",
};

function canonicalIngredientName(input: string): string {
  const raw = String(input || "").trim();
  if (!raw) return "";
  const key = raw.toLowerCase().replace(/\s+/g, " ").trim();
  return INGREDIENT_DISPLAY_MAP[key] || raw;
}

function normalizeIngredientTermsInText(input: string): string {
  let out = String(input || "");
  if (!out) return "";
  for (const [tech, human] of Object.entries(INGREDIENT_DISPLAY_MAP)) {
    const escaped = tech.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(escaped, "gi");
    out = out.replace(re, human);
  }
  return out;
}

type LastAskSnapshot = {
  at?: string;
  response?: AskAgentResponse;
};

type WarehouseLiveSnapshot = {
  at?: string;
  summary?: {
    qty_by_label_kg?: Record<string, number>;
    top_ingredients_kg?: Array<{
      ingredient: string;
      label: string;
      qty_kg: number;
    }>;
  };
};

function readLastAskSnapshot(): LastAskSnapshot | null {
  try {
    const raw = localStorage.getItem("sotipapier_last_ask_agent");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LastAskSnapshot;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function getLastAskDisplayText(response?: AskAgentResponse): string {
  if (!response) return "";
  const raw =
    response.final_response?.trim() ||
    response.reponse_agent?.trim() ||
    response.resultat_agent_brut?.trim() ||
    "Aucun détail disponible.";
  return normalizeIngredientTermsInText(raw);
}

function readWarehouseLiveSnapshot(): WarehouseLiveSnapshot | null {
  try {
    const raw = localStorage.getItem(WAREHOUSE_LIVE_SUMMARY_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as WarehouseLiveSnapshot;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function readWarehouseActiveJobId(): string {
  try {
    return String(localStorage.getItem(WAREHOUSE_ACTIVE_JOB_KEY) || "").trim();
  } catch {
    return "";
  }
}

type StockClassPoint = {
  at: string;
  MP: number;
  CHIMIE: number;
  PDR: number;
  source: "assistant" | "upload live";
};

function readStockClassHistory(): StockClassPoint[] {
  try {
    const raw = localStorage.getItem(STOCK_HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x) => x && typeof x === "object")
      .map((x) => ({
        at: String((x as { at?: unknown }).at || ""),
        MP: Number((x as { MP?: unknown }).MP || 0),
        CHIMIE: Number((x as { CHIMIE?: unknown }).CHIMIE || 0),
        PDR: Number((x as { PDR?: unknown }).PDR || 0),
        source: (
          String((x as { source?: unknown }).source || "").toLowerCase() === "upload live"
            ? "upload live"
            : "assistant"
        ) as "assistant" | "upload live",
      }))
      .filter((x) => x.at);
  } catch {
    return [];
  }
}

function writeStockClassHistory(points: StockClassPoint[]): void {
  try {
    localStorage.setItem(STOCK_HISTORY_KEY, JSON.stringify(points.slice(-STOCK_HISTORY_LIMIT)));
  } catch {
    // ignore localStorage errors
  }
}

export function DashboardPage() {
  const [dashboard, setDashboard] = useState<ProductionDashboardResponse | null>(null);
  const [selectedArticle, setSelectedArticle] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastAsk, setLastAsk] = useState<LastAskSnapshot | null>(() => readLastAskSnapshot());
  const [warehouseLive, setWarehouseLive] = useState<WarehouseLiveSnapshot | null>(() =>
    readWarehouseLiveSnapshot()
  );
  const [warehouseActiveJobId, setWarehouseActiveJobId] = useState<string>(() => readWarehouseActiveJobId());
  const [stockClassHistory, setStockClassHistory] = useState<StockClassPoint[]>(() => readStockClassHistory());

  useEffect(() => {
    // Cleanup legacy key from old frontend versions to prevent stale curves.
    try {
      localStorage.removeItem("sotipapier_stock_class_history");
    } catch {
      // ignore localStorage errors
    }
  }, []);

  useEffect(() => {
    function refreshLastAsk() {
      setLastAsk(readLastAskSnapshot());
    }
    window.addEventListener("sotipapier:ask-agent-updated", refreshLastAsk);
    return () => window.removeEventListener("sotipapier:ask-agent-updated", refreshLastAsk);
  }, []);

  useEffect(() => {
    function refreshWarehouseJob() {
      setWarehouseActiveJobId(readWarehouseActiveJobId());
    }
    function onStorage(event: StorageEvent) {
      if (event.key === WAREHOUSE_ACTIVE_JOB_KEY) {
        refreshWarehouseJob();
      }
    }
    window.addEventListener("sotipapier:warehouse-job-updated", refreshWarehouseJob);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("sotipapier:warehouse-job-updated", refreshWarehouseJob);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    if (!warehouseActiveJobId) {
      // Keep the latest uploaded snapshot if available.
      // Do not force-clear here, otherwise the dashboard falls back to ASSISTANT
      // right after a successful upload completion.
      const latest = readWarehouseLiveSnapshot();
      if (latest?.summary?.qty_by_label_kg && Object.keys(latest.summary.qty_by_label_kg).length > 0) {
        setWarehouseLive(latest);
      }
      return;
    }
  }, [warehouseActiveJobId]);

  useEffect(() => {
    if (!warehouseActiveJobId) return;
    let cancelled = false;
    const t = setInterval(async () => {
      try {
        const job = await getWarehouseIngestionJob(warehouseActiveJobId);
        if (cancelled) return;
        const liveQty = job.qty_by_label_kg || {};
        if (Object.keys(liveQty).length) {
          setWarehouseLive({
            at: new Date().toISOString(),
            summary: { qty_by_label_kg: liveQty },
          });
        }
        const st = String(job.status || "").toLowerCase();
        if (st === "done" || st === "error") {
          const wh = await getWarehouseSummary();
          if (cancelled) return;
          const completedSnapshot = {
            at: new Date().toISOString(),
            summary: {
              qty_by_label_kg: wh.qty_by_label_kg || {},
              top_ingredients_kg: wh.top_ingredients_kg || [],
            },
          };
          setWarehouseLive(completedSnapshot);
          try {
            localStorage.setItem(WAREHOUSE_LIVE_SUMMARY_KEY, JSON.stringify(completedSnapshot));
            window.dispatchEvent(new Event("sotipapier:warehouse-summary-updated"));
          } catch {
            // ignore localStorage errors
          }
          localStorage.removeItem(WAREHOUSE_ACTIVE_JOB_KEY);
          setWarehouseActiveJobId("");
        }
      } catch {
        // ignore polling errors
      }
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [warehouseActiveJobId]);

  useEffect(() => {
    function refreshWarehouseLive() {
      setWarehouseLive(readWarehouseLiveSnapshot());
    }
    function onStorage(event: StorageEvent) {
      if (event.key === WAREHOUSE_LIVE_SUMMARY_KEY) {
        refreshWarehouseLive();
      }
    }
    window.addEventListener("sotipapier:warehouse-summary-updated", refreshWarehouseLive);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("sotipapier:warehouse-summary-updated", refreshWarehouseLive);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    // Fallback hydration: if no active job but a classified warehouse base exists,
    // keep dashboard anchored to real uploaded stock source.
    if (warehouseActiveJobId) return;
    let cancelled = false;
    void (async () => {
      try {
        const wh = await getWarehouseSummary();
        if (cancelled) return;
        const qty = wh.qty_by_label_kg || {};
        if (!Object.keys(qty).length) return;
        const hydrated: WarehouseLiveSnapshot = {
          at: new Date().toISOString(),
          summary: {
            qty_by_label_kg: qty,
            top_ingredients_kg: wh.top_ingredients_kg || [],
          },
        };
        setWarehouseLive(hydrated);
        try {
          localStorage.setItem(WAREHOUSE_LIVE_SUMMARY_KEY, JSON.stringify(hydrated));
          window.dispatchEvent(new Event("sotipapier:warehouse-summary-updated"));
        } catch {
          // ignore localStorage errors
        }
      } catch {
        // ignore summary fallback errors
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [warehouseActiveJobId]);

  useEffect(() => {
    let active = true;
    async function run() {
      setLoading(true);
      setError(null);
      try {
        const data = await getProductionDashboard({
          start_year: 2017,
          max_articles: 6,
          article: selectedArticle || undefined,
        });
        if (active) setDashboard(data);
      } catch (e) {
        const msg =
          e && typeof e === "object" && "message" in e
            ? String((e as { message?: string }).message)
            : "Impossible de charger les tendances production.";
        if (active) setError(msg);
      } finally {
        if (active) setLoading(false);
      }
    }
    run();
    return () => {
      active = false;
    };
  }, [selectedArticle]);

  const lineData = useMemo(() => {
    if (!dashboard) return [];
    const byPeriod = new Map<string, Record<string, string | number>>();
    for (const point of dashboard.monthly_totals) {
      byPeriod.set(point.period, {
        period: point.period,
        total: point.quantity_ton,
      });
    }
    for (const trend of dashboard.article_trends) {
      for (const point of trend.points) {
        const row = byPeriod.get(point.period) || { period: point.period, total: 0 };
        row[trend.article] = point.quantity_ton;
        byPeriod.set(point.period, row);
      }
    }
    return Array.from(byPeriod.values()).sort((a, b) => String(a.period).localeCompare(String(b.period)));
  }, [dashboard]);

  const pieData = useMemo(() => {
    if (!dashboard) return [];
    return dashboard.top_articles.map((x, i) => ({
      name: x.article,
      value: x.quantity_ton,
      color: TREND_COLORS[i % TREND_COLORS.length],
    }));
  }, [dashboard]);

  const stockAlerts = lastAsk?.response?.stock_alerts || [];
  const capacity = lastAsk?.response?.production_capacity;
  const hasAssistantPostConsumption = useMemo(() => {
    const applied = Boolean(lastAsk?.response?.production_applied);
    const inv = (lastAsk?.response?.inventory_dashboard || {}) as Record<string, unknown>;
    const totals = (inv.final_totals_kg || {}) as Record<string, number>;
    return (
      applied &&
      (Number(totals.MP || 0) > 0 || Number(totals.CHIMIE || 0) > 0 || Number(totals.PDR || 0) > 0)
    );
  }, [lastAsk?.response?.inventory_dashboard, lastAsk?.response?.production_applied]);
  const hasWarehouseLiveData = useMemo(() => {
    const live = warehouseLive?.summary?.qty_by_label_kg || {};
    return Object.keys(live).length > 0 && !hasAssistantPostConsumption;
  }, [hasAssistantPostConsumption, warehouseLive?.summary?.qty_by_label_kg]);
  const stockSourceLabel = hasWarehouseLiveData ? "upload live" : "assistant";
  const stockSourceToneClass = hasWarehouseLiveData
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    : "border-cyan-500/35 bg-cyan-500/10 text-cyan-300";
  const stockClassData = useMemo(() => {
    const live = (warehouseLive?.summary?.qty_by_label_kg || {}) as Record<string, number>;
    if (Object.keys(live).length) {
      return {
        MP: Number(live.MP || 0),
        CHIMIE: Number(live.CHIMIE || 0),
        PDR: Number(live.PDR || 0),
      };
    }
    const inv = (lastAsk?.response?.inventory_dashboard || {}) as Record<string, unknown>;
    const finalTotals = (inv.final_totals_kg || {}) as Record<string, number>;
    return {
      MP: Number(finalTotals.MP || 0),
      CHIMIE: Number(finalTotals.CHIMIE || 0),
      PDR: Number(finalTotals.PDR || 0),
    };
  }, [lastAsk?.response?.inventory_dashboard, warehouseLive?.summary?.qty_by_label_kg]);
  const stockClassLineData = useMemo(
    () =>
      stockClassHistory.map((p, idx) => ({
        ...p,
        atLabel: new Date(p.at).toLocaleTimeString("fr-FR", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
        idx,
      })),
    [stockClassHistory]
  );
  const ingredientHistogramData = useMemo(() => {
    const rows = warehouseLive?.summary?.top_ingredients_kg || [];
    const fromUpload = rows
      .filter((r) => Number(r.qty_kg || 0) > 0)
      .slice(0, 12)
      .map((r) => ({
        ingredient: canonicalIngredientName(String(r.ingredient || "N/A")),
        label: String(r.label || "UNKNOWN"),
        qty_kg: Number(r.qty_kg || 0),
      }));
    if (fromUpload.length) return fromUpload;

    const recipeStructured = Array.isArray(lastAsk?.response?.recipe_items) ? lastAsk?.response?.recipe_items : [];
    const fromRecipe = recipeStructured
      .map((item) => ({
        ingredient: canonicalIngredientName(String(item?.ingredient || "N/A")),
        label: "RECIPE",
        qty_kg: Number(
          item?.qty_kg ??
            item?.quantity_kg ??
            item?.required_kg ??
            (String(item?.required_unit || "").toLowerCase().startsWith("t")
              ? Number(item?.required_value ?? 0) * 1000
              : Number(item?.required_value ?? 0))
        ),
      }))
      .filter((r) => Number.isFinite(r.qty_kg) && r.qty_kg > 0)
      .sort((a, b) => b.qty_kg - a.qty_kg)
      .slice(0, 12);
    return fromRecipe;
  }, [lastAsk?.response?.recipe_items, warehouseLive?.summary?.top_ingredients_kg]);
  const displayText = getLastAskDisplayText(lastAsk?.response);

  useEffect(() => {
    const pointAt = warehouseLive?.at || lastAsk?.at;
    if (!pointAt) return;
    const pointSource: "assistant" | "upload live" = hasWarehouseLiveData ? "upload live" : "assistant";
    const next: StockClassPoint = {
      at: String(pointAt),
      MP: stockClassData.MP,
      CHIMIE: stockClassData.CHIMIE,
      PDR: stockClassData.PDR,
      source: pointSource,
    };
    setStockClassHistory((prev) => {
      const last = prev[prev.length - 1];
      // If source changes (assistant <-> upload live), restart series to avoid zig-zag artifacts.
      if (last && last.source !== next.source) {
        const resetSeries = [next];
        writeStockClassHistory(resetSeries);
        return resetSeries;
      }
      if (
        last &&
        Number(last.MP) === Number(next.MP) &&
        Number(last.CHIMIE) === Number(next.CHIMIE) &&
        Number(last.PDR) === Number(next.PDR)
      ) {
        return prev;
      }
      const merged = [...prev, next].slice(-STOCK_HISTORY_LIMIT);
      writeStockClassHistory(merged);
      return merged;
    });
  }, [
    hasWarehouseLiveData,
    lastAsk?.at,
    warehouseLive?.at,
    stockClassData.CHIMIE,
    stockClassData.MP,
    stockClassData.PDR,
  ]);

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <HmiTag tone="cyan">Synoptique</HmiTag>
            <HmiTag tone="muted">Données réelles</HmiTag>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-steel-100 md:text-3xl">
            Centre de contrôle production
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-steel-500">
            Analyse du fichier recette réel depuis 2017 : tendances de quantité produite par article,
            volumétrie cumulée et alertes stock issues des tests Assistant.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-steel-600">
            <Layers className="h-4 w-4 text-plant-accent" />
            Tendances live
          </div>
          <select
            value={selectedArticle}
            onChange={(e) => setSelectedArticle(e.target.value)}
            className="hmi-input w-52 py-1.5 text-xs"
          >
            <option value="">Top articles</option>
            {(dashboard?.article_options || []).map((article) => (
              <option key={article} value={article}>
                {article}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <IndustrialPanel variant="accent" noPadding className="overflow-hidden">
          <div className="p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-steel-500">
                <Package className="h-4 w-4 text-plant-accent" />
                <span className="font-mono text-[10px] uppercase tracking-wider">Articles suivis</span>
              </div>
              <span className="font-mono text-[10px] text-steel-600">INV-01</span>
            </div>
            <p className="mt-3 font-mono text-4xl font-bold tabular-nums text-steel-100">
              {dashboard?.summary.unique_articles?.toLocaleString("fr-FR") || "—"}
            </p>
            <p className="mt-1 text-xs text-steel-600">Familles articles (CSV recette depuis 2017)</p>
          </div>
        </IndustrialPanel>

        <IndustrialPanel variant="warn" noPadding className="overflow-hidden">
          <div className="p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-steel-500">
                <TrendingUp className="h-4 w-4 text-alert-orange" />
                <span className="font-mono text-[10px] uppercase tracking-wider">Alertes</span>
              </div>
              <HmiTag tone="orange">Priorité</HmiTag>
            </div>
            <p className="mt-3 font-mono text-4xl font-bold tabular-nums text-alert-orange">
              {stockAlerts.length}
            </p>
            <p className="mt-1 text-xs text-steel-600">Alertes stock (dernière requête Assistant)</p>
          </div>
        </IndustrialPanel>

        <IndustrialPanel noPadding className="overflow-hidden">
          <div className="p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-steel-500">
                <Activity className="h-4 w-4 text-plant-glow" />
                <span className="font-mono text-[10px] uppercase tracking-wider">Lignes actives</span>
              </div>
              <span className="font-mono text-[10px] text-emerald-500/90">OK</span>
            </div>
            <p className="mt-3 font-mono text-4xl font-bold tabular-nums text-steel-100">
              {dashboard?.summary.active_lines || 0}
            </p>
            <p className="mt-1 text-xs text-steel-600">Lignes actives (dernier mois du CSV)</p>
          </div>
        </IndustrialPanel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <IndustrialPanel
          eyebrow="Graph — production"
          title="Répartition quantité produite"
          subtitle="Top articles cumulés (tonnes) depuis 2017"
          noPadding
          className="overflow-hidden"
        >
          <div className="h-[300px] px-2 pb-2 pt-1">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={56}
                  outerRadius={96}
                  paddingAngle={2}
                >
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} stroke="#050b14" strokeWidth={1} />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend
                  wrapperStyle={{ color: "#9ca3af", fontSize: "11px", paddingTop: "8px" }}
                  formatter={(value) => <span className="font-mono text-steel-400">{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </IndustrialPanel>

        <IndustrialPanel
          eyebrow="Tendance"
          title="Production mensuelle par article"
          subtitle="Courbes depuis 2017 (tonnes)"
          noPadding
          className="overflow-hidden"
        >
          <div className="h-[300px] px-2 pb-2 pt-1">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineData} margin={{ left: 8, right: 14, top: 10, bottom: 2 }}>
                <CartesianGrid stroke="rgba(21,58,92,0.4)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="period"
                  stroke="#4b5563"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  minTickGap={20}
                />
                <YAxis
                  stroke="#4b5563"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  width={44}
                  tickFormatter={(v) => `${Math.round(Number(v))}`}
                />
                <Tooltip cursor={{ fill: "rgba(14, 116, 144, 0.1)" }} contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ color: "#9ca3af", fontSize: "11px" }} />
                {(dashboard?.article_trends || []).map((trend, idx) => (
                  <Line
                    key={trend.article}
                    type="monotone"
                    dataKey={trend.article}
                    stroke={TREND_COLORS[idx % TREND_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </IndustrialPanel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <IndustrialPanel
          eyebrow="Stock réel classifié"
          title="Courbes MP / CHIMIE / PDR"
          subtitle="Temps réel: évolue avec consommation (Passer commande)"
          noPadding
          className="overflow-hidden"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-2">
            <span className={`rounded-sm border px-2 py-1 font-mono text-[10px] uppercase tracking-widest ${stockSourceToneClass}`}>
              source: {stockSourceLabel}
            </span>
            <span className="font-mono text-[10px] text-steel-600">
              maj:{" "}
              {warehouseLive?.at || lastAsk?.at
                ? new Date(String(warehouseLive?.at || lastAsk?.at)).toLocaleTimeString("fr-FR")
                : "—"}
            </span>
          </div>
          <div className="h-[300px] px-2 pb-2 pt-1">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stockClassLineData} margin={{ left: 8, right: 12, top: 8, bottom: 8 }}>
                <CartesianGrid stroke="rgba(21,58,92,0.4)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="atLabel"
                  stroke="#4b5563"
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                  minTickGap={20}
                />
                <YAxis stroke="#4b5563" tick={{ fill: "#9ca3af", fontSize: 10 }} />
                <Tooltip
                  cursor={{ fill: "rgba(14, 116, 144, 0.1)" }}
                  contentStyle={tooltipStyle}
                  formatter={(v: number) => `${Number(v).toFixed(2)} kg`}
                />
                <Legend wrapperStyle={{ color: "#9ca3af", fontSize: "11px" }} />
                <Line type="monotone" dataKey="MP" stroke="#22d3ee" strokeWidth={2} dot={{ r: 2 }} />
                <Line type="monotone" dataKey="CHIMIE" stroke="#f59e0b" strokeWidth={2} dot={{ r: 2 }} />
                <Line type="monotone" dataKey="PDR" stroke="#10b981" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </IndustrialPanel>

        <IndustrialPanel
          eyebrow="Upload stock réel"
          title="Histogramme ingrédients (kg)"
          subtitle="Top ingrédients captés depuis le fichier uploadé"
          noPadding
          className="overflow-hidden"
        >
          <div className="h-[300px] px-2 pb-2 pt-1">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ingredientHistogramData} margin={{ left: 8, right: 12, top: 8, bottom: 8 }}>
                <CartesianGrid stroke="rgba(21,58,92,0.4)" strokeDasharray="3 3" />
                <XAxis dataKey="ingredient" hide />
                <YAxis stroke="#4b5563" tick={{ fill: "#9ca3af", fontSize: 10 }} />
                <Tooltip
                  cursor={{ fill: "rgba(14, 116, 144, 0.1)" }}
                  contentStyle={tooltipStyle}
                  formatter={(v: number) => `${Number(v).toFixed(2)} kg`}
                  labelFormatter={(_, items) => {
                    const row = items?.[0]?.payload as { ingredient?: string; label?: string } | undefined;
                    return `${row?.ingredient || "N/A"} (${row?.label || "UNKNOWN"})`;
                  }}
                />
                <Bar dataKey="qty_kg" fill="#22d3ee" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </IndustrialPanel>

        <IndustrialPanel
          eyebrow="Assistant / recette"
          title="Alerte stock liée au dernier test"
          subtitle="Dépend de la dernière requête envoyée dans la page Assistant"
        >
          {lastAsk?.response ? (
            <div className="space-y-3 text-xs text-steel-500">
              <p>
                Dernier test:{" "}
                <span className="font-mono text-steel-300">
                  {lastAsk.at ? new Date(lastAsk.at).toLocaleString("fr-FR") : "—"}
                </span>
              </p>
              <pre className="whitespace-pre-wrap rounded-sm border border-navy-700 bg-navy-950/70 p-3 text-steel-400">
                {displayText}
              </pre>
              {stockAlerts.length ? (
                <ul className="space-y-2">
                  {stockAlerts.slice(0, 8).map((a, i) => (
                    <li key={i} className="rounded-sm border border-alert-orange/30 bg-alert-orange/5 p-2.5">
                      <span className="font-semibold text-alert-orange">
                        {canonicalIngredientName(String(a.ingredient || "")) || "Ingrédient"}
                      </span>
                      <span className="ml-2 text-steel-400">
                        requis {Number(a.required_kg || 0).toFixed(2)} kg · dispo{" "}
                        {Number(a.available_kg || 0).toFixed(2)} kg · manquant{" "}
                        {Number(a.missing_kg || 0).toFixed(2)} kg
                      </span>
                      <span className="ml-2 font-mono text-[10px] uppercase tracking-widest text-alert-orange/80">
                        {a.severity || "warning"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-sm border border-emerald-500/30 bg-emerald-500/5 p-3 text-emerald-400">
                  Pas d’alerte stock sur le dernier test.
                </p>
              )}
              {capacity && Number.isFinite(Number(capacity.max_producible_tonnage)) ? (
                <div className="rounded-sm border border-cyan-500/30 bg-cyan-500/5 p-3 text-steel-300">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-cyan-300">
                    Estimation capacité (stock réel)
                  </p>
                  <p className="mt-1">
                    Tonnage demandé:{" "}
                    <span className="font-mono">{Number(capacity.requested_tonnage || 0).toFixed(3)} t</span>
                  </p>
                  <p>
                    Tonnage max possible:{" "}
                    <span className="font-mono">
                      {Number(capacity.max_producible_tonnage || 0).toFixed(3)} t
                    </span>
                  </p>
                  <p>
                    Commandes complètes possibles:{" "}
                    <span className="font-mono">{Math.max(0, Number(capacity.full_orders_possible || 0))}</span>
                  </p>
                  <p>
                    Ingrédient limitant:{" "}
                    <span className="font-mono">{capacity.limiting_ingredient || "N/A"}</span>
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-steel-500">
              Lance une requête dans Assistant (ex: recette cannelure 6 tonnes) pour voir les alertes ici.
            </p>
          )}
        </IndustrialPanel>
      </div>

      {loading ? (
        <p className="font-mono text-xs text-steel-500">Chargement des tendances production…</p>
      ) : null}
      {error ? (
        <p className="rounded-sm border border-alert-red/35 bg-alert-red/10 p-3 font-mono text-xs text-alert-red">
          {error}
        </p>
      ) : null}
    </div>
  );
}
