import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Download,
  FileUp,
  RefreshCw,
  Send,
  UploadCloud,
  User,
} from "lucide-react";
import { submitOperatorTurn } from "@/api/harnessOperator";
import { getClassificationJobStatus, uploadClassificationFile } from "@/api/fileClassification";
import { getLongTermMemory, getShortTermMemory, type LongTermMemoryItem, type ShortTermMemoryItem } from "@/api/memory";
import {
  PromptToolStrip,
  resolvePreferredRoute,
  type ToolMode,
} from "@/components/assistant/PromptToolStrip";
import { HmiTag } from "@/components/IndustrialPanel";
import { IndustrialLoader } from "@/components/IndustrialLoader";
import type { AskAgentPayload, AskAgentResponse, StockAlert } from "@/types/askAgent";
import type { FileClassificationJobResponse } from "@/types/fileClassification";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: AskAgentResponse;
}

const ASSISTANT_SESSION_KEY = "sotipapier_assistant_session_id";
const ASSISTANT_DRAFT_KEY = "sotipapier_assistant_draft";

function sessionMessagesStorageKey(sessionId: string): string {
  return `sotipapier_assistant_messages_${sessionId}`;
}

interface ConversationSummary {
  sessionId: string;
  updatedAt: string;
  preview: string;
}

type RecipeVizItem = {
  ingredient: string;
  qtyKg: number;
};

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

function newMessageId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function getAssistantSessionId(): string {
  const existing = localStorage.getItem(ASSISTANT_SESSION_KEY);
  if (existing) return existing;
  const sid = newMessageId().replace("msg-", "sess-");
  localStorage.setItem(ASSISTANT_SESSION_KEY, sid);
  return sid;
}

function saveSessionMessages(sessionId: string, messages: ChatMessage[]): void {
  try {
    localStorage.setItem(sessionMessagesStorageKey(sessionId), JSON.stringify(messages));
  } catch {
    // Ignore localStorage quota/privacy errors
  }
}

function loadSessionMessages(sessionId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(sessionMessagesStorageKey(sessionId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && (item.role === "user" || item.role === "assistant"))
      .map((item, idx) => ({
        id: String(item.id || `cached-${sessionId}-${idx}`),
        role: item.role === "assistant" ? "assistant" : "user",
        content:
          item.role === "assistant"
            ? normalizeIngredientTermsInText(String(item.content || ""))
            : String(item.content || ""),
        response: item.response || undefined,
      }));
  } catch {
    return [];
  }
}

function parseRecipeItems(response: AskAgentResponse | null): RecipeVizItem[] {
  const structured = Array.isArray(response?.recipe_items) ? response?.recipe_items : [];
  if (structured.length) {
    const rows: RecipeVizItem[] = structured
      .map((item) => ({
        ingredient: canonicalIngredientName(String(item?.ingredient || "").trim()),
        qtyKg: Number(
          item?.qty_kg ??
            item?.quantity_kg ??
            item?.required_kg ??
            (String(item?.required_unit || "").toLowerCase().startsWith("t")
              ? Number(item?.required_value ?? 0) * 1000
              : Number(item?.required_value ?? 0))
        ),
      }))
      .filter((x) => x.ingredient && Number.isFinite(x.qtyKg) && x.qtyKg > 0)
      .sort((a, b) => b.qtyKg - a.qtyKg);
    if (rows.length) return rows;
  }

  const raw = [response?.resultat_agent_brut, response?.final_response, response?.reponse_agent]
    .map((x) => String(x || "").trim())
    .filter(Boolean)
    .join("\n");
  if (!raw) return [];
  const rows: RecipeVizItem[] = [];
  const byIngredient = new Map<string, number>();
  const lines = raw.split("\n");

  function normalizeIngredient(input: string): string {
    return canonicalIngredientName(
      input
      .replace(/^[\-*•\d.\)\s]+/, "")
      .replace(/^\|\s*/, "")
      .replace(/\s*\|.*$/, "")
      .replace(/\s+/g, " ")
      .trim()
    );
  }

  function pushRow(ingredientRaw: string, valueRaw: string, unitRaw: string): void {
    const ingredient = normalizeIngredient(ingredientRaw);
    const value = Number(String(valueRaw || "0").replace(",", "."));
    const unit = String(unitRaw || "kg").toLowerCase();
    const qtyKg = unit === "kg" ? value : value * 1000;
    if (!ingredient || !Number.isFinite(qtyKg) || qtyKg <= 0) return;
    byIngredient.set(ingredient, (byIngredient.get(ingredient) || 0) + qtyKg);
  }

  // Format 1: "1 - Amidon : 450 kg"
  const numberedPattern =
    /^\s*\d+\s*[-.)]\s*(.+?)\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|tonne|tonnes|t)\b/i;
  // Format 2: "- Amidon : 450 kg"
  const bulletPattern =
    /^\s*[-*•]\s*(.+?)\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|tonne|tonnes|t)\b/i;
  // Format 3: markdown table "| Amidon | 450 | kg |"
  const tablePattern =
    /^\s*\|\s*([^|]+?)\s*\|\s*([0-9]+(?:[.,][0-9]+)?)\s*\|\s*(kg|tonne|tonnes|t)\s*\|?\s*$/i;
  // Format 4: free text "Amidon ... 450 kg"
  const loosePattern =
    /^\s*(.+?)\s+([0-9]+(?:[.,][0-9]+)?)\s*(kg|tonne|tonnes|t)\b/i;

  for (const line of lines) {
    const l = line.trim();
    if (!l) continue;
    if (/^[-|:\s]+$/.test(l)) continue;
    if (/ingrédient|ingredient|quantité|quantite|recette/i.test(l) && !/\d/.test(l)) continue;
    if (/^la commande\b/i.test(l)) continue;
    if (/^quantité\b/i.test(l)) continue;

    let m = l.match(numberedPattern);
    if (m) {
      pushRow(m[1], m[2], m[3]);
      continue;
    }
    m = l.match(bulletPattern);
    if (m) {
      pushRow(m[1], m[2], m[3]);
      continue;
    }
    m = l.match(tablePattern);
    if (m) {
      pushRow(m[1], m[2], m[3]);
      continue;
    }
    m = l.match(loosePattern);
    if (m) {
      pushRow(m[1], m[2], m[3]);
      continue;
    }
  }

  for (const [ingredient, qtyKg] of byIngredient.entries()) {
    rows.push({ ingredient, qtyKg });
  }
  return rows.sort((a, b) => b.qtyKg - a.qtyKg);
}

function parseRecipeError(response: AskAgentResponse | null): string {
  const raw = [response?.resultat_agent_brut, response?.final_response, response?.reponse_agent]
    .map((x) => String(x || ""))
    .join("\n");
  const markers = ["Erreur agent recette:", "Échec de l'extraction", "ECHEC EXTRACTION RECETTE"];
  for (const marker of markers) {
    const idx = raw.indexOf(marker);
    if (idx >= 0) return raw.slice(idx).trim();
  }
  return "";
}

function StockAlertsCard({ alerts }: { alerts: StockAlert[] }) {
  return (
    <div className="rounded-sm border border-alert-red/55 bg-gradient-to-br from-alert-red/15 to-navy-950 p-4 shadow-[inset_0_0_40px_-20px_rgba(220,38,38,0.35)]">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <AlertTriangle className="h-5 w-5 shrink-0 text-alert-red" />
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.15em] text-alert-red">
          Alarme stock
        </span>
        <HmiTag tone="orange">Critique</HmiTag>
      </div>
      <ul className="space-y-2 text-sm text-steel-200">
        {alerts.map((a, i) => (
          <li
            key={i}
            className="rounded-sm border border-alert-red/35 bg-navy-950/70 px-3 py-2 font-mono text-xs"
          >
            <span className="font-semibold text-steel-200">
              {canonicalIngredientName(String(a.ingredient || "")) || "Ingrédient"}
            </span>
            {a.missing_kg != null ? (
              <span className="mt-1 block text-alert-orange">
                Manquant : {Number(a.missing_kg).toFixed(2)} kg
                {a.available_kg != null
                  ? ` (dispo : ${Number(a.available_kg).toFixed(2)} kg)`
                  : ""}
              </span>
            ) : null}
            {a.required_kg != null ? (
              <span className="block text-steel-500">
                Requis : {Number(a.required_kg).toFixed(2)} kg
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function WorkflowResponseCard({ response }: { response: AskAgentResponse }) {
  const recipeItems = parseRecipeItems(response);
  const alerts = Array.isArray(response.stock_alerts) ? response.stock_alerts : [];
  const capacity = response.production_capacity;
  const prediction = response.stock_prediction;
  const tools = [
    `Tool Classification MP/PDR: ${response.statut_classification || "INCONNU"}`,
    `Tool Classification MP/CHIMIE (si MP): ${response.categorie_cible || "N/A"}`,
    "Tool Recette: exécuté",
    "Tool Contrôle stock: exécuté",
    "Sous-agent prédiction stock (ML): exécuté",
  ];

  return (
    <div className="space-y-3">
      <div className="rounded-sm border border-navy-700 bg-navy-950/70 px-3 py-2">
        <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">Titre</p>
        <p className="text-sm font-semibold text-steel-200">
          {alerts.length ? "ALERTE PRODUCTION" : "VALIDATION PRODUCTION"}
        </p>
      </div>

      <div className="rounded-sm border border-navy-700 bg-navy-950/70 px-3 py-2">
        <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">Tools activés</p>
        <ul className="mt-1 space-y-1 text-xs text-steel-300">
          {tools.map((t) => (
            <li key={t}>- {t}</li>
          ))}
        </ul>
      </div>

      {recipeItems.length ? (
        <div className="rounded-sm border border-navy-700 bg-navy-950/70 px-3 py-2">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-steel-600">
            Recette (quantités requises)
          </p>
          <div className="hmi-scrollbar max-h-44 overflow-auto rounded-sm border border-navy-800">
            <table className="w-full text-left text-[11px] text-steel-300">
              <thead className="sticky top-0 bg-navy-950">
                <tr>
                  <th className="px-2 py-1">Ingrédient</th>
                  <th className="px-2 py-1">Quantité (kg)</th>
                </tr>
              </thead>
              <tbody>
                {recipeItems.map((item, idx) => (
                  <tr key={`${item.ingredient}-${idx}`} className="border-t border-navy-900">
                    <td className="px-2 py-1">{item.ingredient}</td>
                    <td className="px-2 py-1 font-mono">{item.qtyKg.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {capacity && Number.isFinite(Number(capacity.max_producible_tonnage)) ? (
        <div className="rounded-sm border border-cyan-700/60 bg-navy-950/70 px-3 py-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-cyan-300">
            Estimation capacité réel stock
          </p>
          <div className="mt-1 space-y-1 text-xs text-steel-300">
            <p>
              Tonnage demandé:{" "}
              <span className="font-mono">{Number(capacity.requested_tonnage || 0).toFixed(3)} t</span>
            </p>
            <p>
              Tonnage max possible:{" "}
              <span className="font-mono">{Number(capacity.max_producible_tonnage || 0).toFixed(3)} t</span>
            </p>
            <p>
              Commandes complètes possibles:{" "}
              <span className="font-mono">{Math.max(0, Number(capacity.full_orders_possible || 0))}</span>
            </p>
            <p>
              Ingrédient limitant: <span className="font-mono">{capacity.limiting_ingredient || "N/A"}</span>
            </p>
          </div>
        </div>
      ) : null}

      {prediction?.predicted_totals_kg ? (
        <div className="rounded-sm border border-violet-700/60 bg-navy-950/70 px-3 py-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-violet-300">
            Prédiction stock (ML dynamique)
          </p>
          <div className="mt-1 space-y-1 text-xs text-steel-300">
            <p>
              Modèle: <span className="font-mono">{prediction.model || "linear_trend_regression"}</span>
            </p>
            <p>
              Sous-agent ML:{" "}
              <span className="font-mono">{prediction.auto_retrained ? "auto-retrain exécuté" : "actif"}</span>
            </p>
            <p>
              Historique utilisé: <span className="font-mono">{Number(prediction.history_points || 0)}</span>{" "}
              points
            </p>
            <p>
              Modèle entraîné sur: <span className="font-mono">{Number(prediction.trained_points || 0)}</span>{" "}
              points
            </p>
            <p>
              Dernier entraînement: <span className="font-mono">{prediction.trained_at || "N/A"}</span>
            </p>
            <p>
              Stock actuel MP/CHIMIE/PDR:{" "}
              <span className="font-mono">
                {Number(prediction.current_totals_kg?.MP || 0).toFixed(2)} /{" "}
                {Number(prediction.current_totals_kg?.CHIMIE || 0).toFixed(2)} /{" "}
                {Number(prediction.current_totals_kg?.PDR || 0).toFixed(2)} kg
              </span>
            </p>
            <p>
              Prévision MP:{" "}
              <span className="font-mono">{Number(prediction.predicted_totals_kg.MP || 0).toFixed(2)} kg</span>{" "}
              ({prediction.depletion_risk?.MP || "stable"}) Δ=
              {Number(prediction.projected_delta_kg?.MP || 0).toFixed(2)} kg, conf=
              {Number(prediction.confidence_score?.MP || 0).toFixed(2)}
            </p>
            <p>
              Prévision CHIMIE:{" "}
              <span className="font-mono">
                {Number(prediction.predicted_totals_kg.CHIMIE || 0).toFixed(2)} kg
              </span>{" "}
              ({prediction.depletion_risk?.CHIMIE || "stable"}) Δ=
              {Number(prediction.projected_delta_kg?.CHIMIE || 0).toFixed(2)} kg, conf=
              {Number(prediction.confidence_score?.CHIMIE || 0).toFixed(2)}
            </p>
            <p>
              Prévision PDR:{" "}
              <span className="font-mono">{Number(prediction.predicted_totals_kg.PDR || 0).toFixed(2)} kg</span>{" "}
              ({prediction.depletion_risk?.PDR || "stable"}) Δ=
              {Number(prediction.projected_delta_kg?.PDR || 0).toFixed(2)} kg, conf=
              {Number(prediction.confidence_score?.PDR || 0).toFixed(2)}
            </p>
          </div>
        </div>
      ) : null}

      <div className="rounded-sm border border-navy-700 bg-navy-950/70 px-3 py-2">
        <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">Alertes stock</p>
        {alerts.length ? (
          <ul className="mt-1 space-y-1 text-xs text-alert-orange">
            {alerts.map((a, idx) => (
              <li key={`${a.ingredient}-${idx}`}>
                - {canonicalIngredientName(String(a.ingredient || ""))}: requis=
                {Number(a.required_kg || 0).toFixed(2)} kg, disponible=
                {Number(a.available_kg || 0).toFixed(2)} kg, manquant={Number(a.missing_kg || 0).toFixed(2)} kg
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-steel-400">Aucune alerte.</p>
        )}
      </div>
    </div>
  );
}

export function AssistantPage() {
  const [idArticle, setIdArticle] = useState("ERP-TEST-001");
  const [description, setDescription] = useState("Cannelure (Fluting)");
  const [categorie, setCategorie] = useState("production");
  const [input, setInput] = useState(() => localStorage.getItem(ASSISTANT_DRAFT_KEY) || "");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState<AskAgentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toolMode, setToolMode] = useState<ToolMode>("auto");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [job, setJob] = useState<FileClassificationJobResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [longHistory, setLongHistory] = useState<LongTermMemoryItem[]>([]);
  const [shortHistory, setShortHistory] = useState<ShortTermMemoryItem[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => getAssistantSessionId());
  const [conversationLoading, setConversationLoading] = useState(false);

  const lastQuestionRef = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  };

  useEffect(() => {
    if (!job?.job_id) return;
    if (job.status !== "queued" && job.status !== "running") return;
    const timer = setInterval(async () => {
      try {
        const next = await getClassificationJobStatus(job.job_id, 120);
        setJob(next);
      } catch {
        // keep polling; transient network glitches happen
      }
    }, 1200);
    return () => clearInterval(timer);
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    try {
      localStorage.setItem(ASSISTANT_DRAFT_KEY, input);
    } catch {
      // Ignore localStorage errors
    }
  }, [input]);

  useEffect(() => {
    if (!activeSessionId) return;
    saveSessionMessages(activeSessionId, messages);
  }, [activeSessionId, messages]);

  useEffect(() => {
    let cancelled = false;
    async function hydrateSession(): Promise<void> {
      if (!activeSessionId) return;

      const cached = loadSessionMessages(activeSessionId);
      if (cached.length && !cancelled) {
        setMessages(cached);
        return;
      }

      try {
        const st = await getShortTermMemory(activeSessionId, 80);
        if (cancelled) return;
        const restored: ChatMessage[] = st
          .filter((item) => item.role === "user" || item.role === "assistant")
          .map((item) => ({
            id: `restored-${item.id}`,
            role: item.role === "assistant" ? "assistant" : "user",
            content: item.content || "",
          }));
        setMessages(restored);
      } catch {
        // Keep current UI state on transient failure
      }
    }
    void hydrateSession();
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  const runAsk = useCallback(
    async (payload: AskAgentPayload) => {
      setLoading(true);
      setError(null);
      try {
        const data = await submitOperatorTurn(payload);
        setLastResponse(data);
        const text =
          (data.final_response || data.reponse_agent || "").trim() ||
          "(Réponse vide du serveur)";
        setMessages((m) => [
          ...m,
          {
            id: newMessageId(),
            role: "assistant",
            content: normalizeIngredientTermsInText(text),
            response: data,
          },
        ]);
        try {
          const sessionId = payload.session_id || getAssistantSessionId();
          const [lt, st] = await Promise.all([
            getLongTermMemory("ask_agent_outputs", 80),
            getShortTermMemory(sessionId, 12),
          ]);
          setLongHistory(lt);
          setShortHistory(st);
          setActiveSessionId(sessionId);
        } catch {
          // non bloquant pour le chat
        }
        scrollToBottom();
      } catch (e: unknown) {
        const msg =
          e && typeof e === "object" && "message" in e
            ? String((e as { message?: string }).message)
            : "Erreur réseau ou serveur.";
        setError(msg);
        setMessages((m) => [
          ...m,
          {
            id: newMessageId(),
            role: "assistant",
            content: `Erreur : ${msg}`,
          },
        ]);
      } finally {
        setLoading(false);
        scrollToBottom();
      }
    },
    []
  );

  const refreshHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const sessionId = activeSessionId || getAssistantSessionId();
      const [lt, st] = await Promise.all([
        getLongTermMemory("ask_agent_outputs", 80),
        getShortTermMemory(sessionId, 12),
      ]);
      setLongHistory(lt);
      setShortHistory(st);

      const bySession = new Map<string, ConversationSummary>();
      for (const item of lt) {
        const sidRaw = item.metadata?.session_id;
        const sid = typeof sidRaw === "string" ? sidRaw.trim() : "";
        if (!sid) continue;
        const existing = bySession.get(sid);
        const candidate: ConversationSummary = {
          sessionId: sid,
          updatedAt: item.updated_at || "",
          preview: String(item.memory_value || "").replace(/\s+/g, " ").slice(0, 90),
        };
        if (!existing || candidate.updatedAt > existing.updatedAt) {
          bySession.set(sid, candidate);
        }
      }
      const rows = Array.from(bySession.values()).sort((a, b) =>
        String(b.updatedAt).localeCompare(String(a.updatedAt))
      );
      setConversations(rows);
    } finally {
      setHistoryLoading(false);
    }
  }, [activeSessionId]);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  async function handleOpenConversation(sessionId: string) {
    if (!sessionId || conversationLoading) return;
    setConversationLoading(true);
    try {
      const st = await getShortTermMemory(sessionId, 80);
      localStorage.setItem(ASSISTANT_SESSION_KEY, sessionId);
      setActiveSessionId(sessionId);
      setShortHistory(st);
      setLastResponse(null);
      const restored: ChatMessage[] = st
        .filter((item) => item.role === "user" || item.role === "assistant")
        .map((item) => ({
          id: `restored-${item.id}`,
          role: item.role === "assistant" ? "assistant" : "user",
          content: item.content || "",
        }));
      setMessages(restored);
      scrollToBottom();
    } finally {
      setConversationLoading(false);
    }
  }

  function handleNewConversation() {
    const sid = newMessageId().replace("msg-", "sess-");
    localStorage.setItem(ASSISTANT_SESSION_KEY, sid);
    setActiveSessionId(sid);
    setMessages([]);
    setShortHistory([]);
    setLastResponse(null);
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q || loading) return;

    lastQuestionRef.current = q;
    setMessages((m) => [...m, { id: newMessageId(), role: "user", content: q }]);
    setInput("");
    scrollToBottom();

    const preferred = resolvePreferredRoute(toolMode, q);
    const payload: AskAgentPayload = {
      id_article_erp: idArticle.trim() || "—",
      description: description.trim() || "—",
      categorie: categorie.trim(),
      question_operateur: q,
      session_id: activeSessionId || getAssistantSessionId(),
      confirm_production: false,
      confirmation_token: "",
    };
    if (preferred) payload.preferred_route = preferred;
    await runAsk(payload);
  }

  async function handleConfirmProduction() {
    const token = lastResponse?.confirmation_token;
    if (!token || loading) return;
    setMessages((m) => [
      ...m,
      {
        id: newMessageId(),
        role: "user",
        content: "Confirmation de production (opérateur)",
      },
    ]);
    scrollToBottom();
    await runAsk({
      id_article_erp: idArticle.trim() || "—",
      description: description.trim() || "—",
      categorie: categorie.trim(),
      question_operateur: lastQuestionRef.current || "Confirmation production",
      session_id: activeSessionId || getAssistantSessionId(),
      confirm_production: true,
      confirmation_token: token,
      preferred_route: "recette",
    });
  }

  function handleRejectProduction() {
    if (!lastResponse) return;
    setMessages((m) => [
      ...m,
      { id: newMessageId(), role: "user", content: "Refus de production (opérateur)" },
      {
        id: newMessageId(),
        role: "assistant",
        content: "Commande refusée. Stock inchangé, estimation conservée en temps réel.",
      },
    ]);
    setLastResponse({
      ...lastResponse,
      confirmation_required: false,
      final_response:
        (lastResponse.final_response || lastResponse.reponse_agent || "").trim() +
        "\n\nCommande refusée par opérateur. Stock inchangé.",
    });
    scrollToBottom();
  }

  async function handleStartFileClassification() {
    if (!uploadFile || uploading) return;
    setUploadError(null);
    setUploading(true);
    try {
      const created = await uploadClassificationFile(uploadFile, categorie.trim());
      setJob(created);
    } catch (e: unknown) {
      const msg =
        e && typeof e === "object" && "message" in e
          ? String((e as { message?: string }).message)
          : "Upload impossible.";
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  }

  const alerts = lastResponse?.stock_alerts?.length
    ? lastResponse.stock_alerts
    : [];
  const showAlerts = alerts.length > 0;
  const recipeItems = parseRecipeItems(lastResponse);
  const recipeError = parseRecipeError(lastResponse);
  const recipeChartData = [...recipeItems]
    .sort((a, b) => b.qtyKg - a.qtyKg)
    .slice(0, 10)
    .map((x) => ({
      ingredient: x.ingredient,
      qtyKg: Number(x.qtyKg.toFixed(2)),
    }));
  const needConfirm = Boolean(lastResponse?.confirmation_required);
  const canConfirm =
    needConfirm &&
    Boolean(lastResponse?.confirmation_token) &&
    !lastResponse?.production_applied;
  const hasRecipeDecisionContext = Boolean(
    lastResponse &&
      (lastResponse.route_intent === "workflow" || lastResponse.route_intent === "recette") &&
      recipeItems.length > 0 &&
      !lastResponse.production_applied
  );

  function handleDownloadHistory() {
    const payload = {
      exported_at: new Date().toISOString(),
      long_term_outputs: longHistory,
      short_term_session: shortHistory,
      last_response_excerpt: lastResponse
        ? {
            route_intent: lastResponse.route_intent,
            statut_classification: lastResponse.statut_classification,
            categorie_cible: lastResponse.categorie_cible,
            final_response: lastResponse.final_response,
          }
        : null,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sotipapier-history-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 lg:flex-row lg:items-stretch">
      <section className="relative flex min-h-[420px] min-w-0 flex-1 flex-col overflow-hidden rounded-sm border border-navy-700/90 bg-gradient-to-b from-navy-900/90 to-navy-950 shadow-[0_0_40px_-16px_rgba(34,211,238,0.2)]">
        <span className="pointer-events-none absolute left-0 top-0 z-10 h-4 w-4 border-l-2 border-t-2 border-plant-accent/80" aria-hidden />
        <span className="pointer-events-none absolute right-0 top-0 z-10 h-4 w-4 border-r-2 border-t-2 border-plant-accent/40" aria-hidden />

        <header className="relative border-b border-navy-800 bg-navy-950/60 px-4 py-4">
          <div className="mb-2 flex flex-wrap gap-2">
            <HmiTag tone="cyan">Console IA</HmiTag>
            <HmiTag tone="muted">Orchestrateur FastAPI</HmiTag>
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-steel-100">Assistant production</h1>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-steel-500">
            Pré-routage local + <code className="text-steel-400">preferred_route</code> vers le cerveau :
            classification (API fine-tunée), recette, ou mode général.
          </p>
        </header>

        <div className="grid gap-3 border-b border-navy-800/90 bg-navy-950/30 p-3 sm:grid-cols-3">
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
              ID ERP
            </label>
            <input
              value={idArticle}
              onChange={(e) => setIdArticle(e.target.value)}
              className="hmi-input w-full text-xs"
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
              Description article
            </label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="hmi-input w-full text-xs"
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
              Zone / machine
            </label>
            <input
              value={categorie}
              onChange={(e) => setCategorie(e.target.value)}
              className="hmi-input w-full text-xs"
            />
          </div>
        </div>

        <div className="border-b border-navy-800/90 bg-navy-950/35 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-steel-400">
              <FileUp className="h-4 w-4 text-plant-accent" />
              <span className="font-mono text-[11px] uppercase tracking-wider">
                Upload fichier classification MP/PDR/CHIMIE
              </span>
            </div>
            <HmiTag tone={toolMode === "classification" ? "cyan" : "muted"}>
              {toolMode === "classification" ? "Tool Classification ON" : "Tool OFF"}
            </HmiTag>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="hmi-input flex h-10 cursor-pointer items-center gap-2 px-3 py-0 text-xs">
              <UploadCloud className="h-4 w-4 text-steel-500" />
              <span className="truncate text-steel-400">
                {uploadFile ? uploadFile.name : "Choisir fichier CSV/XLSX pièces de rechange"}
              </span>
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              />
            </label>
            <button
              type="button"
              onClick={handleStartFileClassification}
              disabled={!uploadFile || uploading}
              className="rounded-sm border border-plant-accent/40 bg-plant-accent/10 px-4 py-2 text-xs font-semibold text-plant-glow transition hover:bg-plant-accent/20 disabled:opacity-40"
            >
              {uploading ? "Upload..." : "Classer le fichier"}
            </button>
          </div>

          {uploadError ? (
            <p className="mt-2 rounded-sm border border-alert-red/40 bg-alert-red/10 px-2 py-1 font-mono text-[11px] text-alert-red">
              {uploadError}
            </p>
          ) : null}

          {job ? (
            <div className="mt-3 rounded-sm border border-navy-700 bg-navy-950/70 p-2.5">
              <div className="mb-1 flex items-center justify-between text-[11px] text-steel-500">
                <span className="font-mono">{job.filename}</span>
                <span className="font-mono uppercase">{job.status}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-sm bg-navy-800">
                <div
                  className="h-full bg-gradient-to-r from-plant-accent to-cyan-500 transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, job.progress_pct || 0))}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-steel-500">
                {job.processed_rows}/{job.total_rows} lignes ({job.progress_pct.toFixed(1)}%)
              </p>
              <div className="mt-2 grid grid-cols-4 gap-2 text-[10px] font-mono text-steel-500">
                <span>MP: {job.counts.MP || 0}</span>
                <span>PDR: {job.counts.PDR || 0}</span>
                <span>CHIMIE: {job.counts.CHIMIE || 0}</span>
                <span>ERR: {job.counts.ERROR || 0}</span>
              </div>
              {job.recent_results.length ? (
                <div className="hmi-scrollbar mt-2 max-h-40 overflow-auto rounded-sm border border-navy-800">
                  <table className="w-full text-left text-[10px] text-steel-500">
                    <thead className="sticky top-0 bg-navy-950">
                      <tr>
                        <th className="px-2 py-1">Article</th>
                        <th className="px-2 py-1">MP/PDR</th>
                        <th className="px-2 py-1">MP/CHIMIE</th>
                        <th className="px-2 py-1">Final</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.recent_results.slice(-30).map((r, idx) => (
                        <tr key={`${r.id_article_erp}-${idx}`} className="border-t border-navy-900">
                          <td className="px-2 py-1">{r.id_article_erp}</td>
                          <td className="px-2 py-1">{r.stage1_mp_pdr}</td>
                          <td className="px-2 py-1">{r.stage2_mp_chimie}</td>
                          <td className="px-2 py-1">{r.final_label}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div ref={scrollRef} className="hmi-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="rounded-sm border border-dashed border-navy-700 bg-navy-950/40 px-4 py-8 text-center">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-steel-600">Zone de consigne</p>
              <p className="mt-2 text-sm text-steel-500">
                Ex. « Classer cette matière : MP ou PDR » · « Recette pour 10 t de Cannelure »
              </p>
            </div>
          ) : null}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role === "assistant" ? (
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-plant-accent/30 bg-plant-accent/15 text-plant-glow shadow-[0_0_16px_-6px_rgba(34,211,238,0.5)]">
                  <Bot className="h-4 w-4" />
                </div>
              ) : null}
              <div
                className={`max-w-[88%] px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user" ? "hmi-chat-user" : "hmi-chat-agent"
                }`}
              >
                {msg.role === "assistant" &&
                msg.response &&
                (msg.response.route_intent === "workflow" || msg.response.route_intent === "recette") ? (
                  <WorkflowResponseCard response={msg.response} />
                ) : (
                  <p className="whitespace-pre-wrap">{normalizeIngredientTermsInText(msg.content)}</p>
                )}
              </div>
              {msg.role === "user" ? (
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-navy-600 bg-navy-800 text-steel-400">
                  <User className="h-4 w-4" />
                </div>
              ) : null}
            </div>
          ))}
          {loading ? <IndustrialLoader label="Orchestration agents & LLM…" /> : null}
        </div>

        {error ? (
          <p className="border-t border-alert-red/30 bg-alert-red/10 px-4 py-2 font-mono text-xs text-alert-red">
            {error}
          </p>
        ) : null}

        <PromptToolStrip
          draftText={input}
          toolMode={toolMode}
          onToolModeChange={setToolMode}
        />

        <form onSubmit={handleSend} className="flex gap-2 border-t border-navy-800 bg-navy-950/40 p-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Consigne opérateur — ex. classification MP/PDR, recette, tonnage…"
            disabled={loading}
            className="hmi-input min-w-0 flex-1 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex shrink-0 items-center gap-2 rounded-sm bg-gradient-to-r from-plant-accent to-cyan-600 px-4 py-2.5 text-sm font-semibold text-navy-950 shadow-[0_0_20px_-6px_rgba(34,211,238,0.6)] transition hover:brightness-110 disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
            Envoyer
          </button>
        </form>
      </section>

      <aside className="flex w-full shrink-0 flex-col gap-4 overflow-y-auto rounded-sm border border-navy-700/90 bg-gradient-to-b from-navy-900/85 to-navy-950 p-4 shadow-panel lg:w-[400px]">
        <div className="flex items-center justify-between gap-2 border-b border-navy-800 pb-3">
          <div className="flex items-center gap-2 text-steel-400">
            <ChevronRight className="h-4 w-4 text-plant-accent" />
            <span className="font-mono text-[11px] uppercase tracking-[0.18em]">Diagnostic réponse</span>
          </div>
          <HmiTag tone="muted">PLC view</HmiTag>
        </div>

        {showAlerts ? <StockAlertsCard alerts={alerts} /> : null}

        {hasRecipeDecisionContext && lastResponse ? (
          <div className="rounded-sm border border-emerald-600/45 bg-gradient-to-br from-emerald-950/50 to-navy-950 p-4 shadow-[inset_0_0_30px_-12px_rgba(16,185,129,0.25)]">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
              <span className="font-mono text-[11px] font-semibold uppercase tracking-wide">
                Validation production
              </span>
              <HmiTag tone="cyan">Attente opérateur</HmiTag>
            </div>
            <p className="text-xs text-steel-500">
              Décrémentation stock uniquement après confirmation explicite.
            </p>
            {canConfirm ? (
              <div className="mt-4 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={handleConfirmProduction}
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-sm bg-gradient-to-r from-emerald-600 to-emerald-500 py-3 text-sm font-bold text-white shadow-[0_0_24px_-8px_rgba(16,185,129,0.7)] transition hover:brightness-110 disabled:opacity-50"
                >
                  <CheckCircle2 className="h-5 w-5" />
                  Passer
                </button>
                <button
                  type="button"
                  onClick={handleRejectProduction}
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-sm border border-alert-orange/60 bg-alert-orange/10 py-3 text-sm font-bold text-alert-orange transition hover:bg-alert-orange/20 disabled:opacity-50"
                >
                  Refuser
                </button>
              </div>
            ) : lastResponse.production_applied ? (
              <p className="mt-3 text-xs font-medium text-emerald-400">
                Production déjà appliquée (stock décrémenté).
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                <p className="text-xs text-alert-orange">
                  Validation impossible actuellement (alerte stock ou token non disponible).
                </p>
                <button
                  type="button"
                  onClick={handleRejectProduction}
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-sm border border-alert-orange/60 bg-alert-orange/10 py-2.5 text-sm font-bold text-alert-orange transition hover:bg-alert-orange/20 disabled:opacity-50"
                >
                  Refuser
                </button>
              </div>
            )}
            {lastResponse.confirmation_token ? (
              <p className="mt-2 break-all font-mono text-[10px] text-steel-600">
                Token : {lastResponse.confirmation_token}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-3 shadow-inner">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-steel-600">
            Payload API (extrait)
          </p>
          <pre className="hmi-scrollbar max-h-48 overflow-auto text-[10px] leading-relaxed text-steel-500">
            {lastResponse
              ? JSON.stringify(lastResponse, null, 2).slice(0, 4000)
              : "Aucune réponse encore."}
            {lastResponse && JSON.stringify(lastResponse).length > 4000 ? "\n…" : ""}
          </pre>
        </div>

        {lastResponse ? (
          <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-3 shadow-inner">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-steel-600">
              Visualisation recette (kg)
            </p>
            {recipeItems.length ? (
              <>
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={recipeChartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke="rgba(21,58,92,0.35)" strokeDasharray="3 3" />
                      <XAxis dataKey="ingredient" hide />
                      <YAxis
                        stroke="#4b5563"
                        tick={{ fill: "#9ca3af", fontSize: 10 }}
                        tickFormatter={(v) => `${Math.round(Number(v))}`}
                      />
                      <Tooltip
                        cursor={{ fill: "rgba(14, 116, 144, 0.12)" }}
                        contentStyle={{
                          backgroundColor: "#0a1628",
                          border: "1px solid #153a5c",
                          borderRadius: "2px",
                          color: "#e5e7eb",
                          fontSize: "12px",
                        }}
                        formatter={(v: number) => `${Number(v).toFixed(2)} kg`}
                        labelFormatter={(_, items) => String(items?.[0]?.payload?.ingredient || "")}
                      />
                      <Bar dataKey="qtyKg" fill="#22d3ee" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="hmi-scrollbar mt-2 max-h-40 overflow-auto rounded-sm border border-navy-800">
                  <table className="w-full text-left text-[10px] text-steel-500">
                    <thead className="sticky top-0 bg-navy-950">
                      <tr>
                        <th className="px-2 py-1">Ingrédient</th>
                        <th className="px-2 py-1">Quantité (kg)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipeItems.map((item, idx) => (
                        <tr key={`${item.ingredient}-${idx}`} className="border-t border-navy-900">
                          <td className="px-2 py-1">{item.ingredient}</td>
                          <td className="px-2 py-1 font-mono text-steel-300">
                            {item.qtyKg.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="rounded-sm border border-alert-orange/40 bg-alert-orange/10 px-3 py-2 text-xs text-alert-orange">
                {recipeError
                  ? `Recette indisponible: ${recipeError.slice(0, 260)}${recipeError.length > 260 ? "…" : ""}`
                  : "Aucune donnée recette détectée dans la dernière réponse."}
              </div>
            )}
          </div>
        ) : null}

        <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-3 shadow-inner">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">
              Historique mémoire
            </p>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleDownloadHistory}
                className="inline-flex items-center gap-1 rounded-sm border border-navy-700 px-2 py-1 text-[10px] text-steel-500 hover:bg-navy-900"
                title="Télécharger historique mémoire"
              >
                <Download className="h-3 w-3" />
                Download
              </button>
              <button
                type="button"
                onClick={() => void refreshHistory()}
                className="inline-flex items-center gap-1 rounded-sm border border-navy-700 px-2 py-1 text-[10px] text-steel-500 hover:bg-navy-900"
              >
                <RefreshCw className={`h-3 w-3 ${historyLoading ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>
          </div>

          <div className="mb-3 space-y-2">
            <div className="flex items-center justify-between">
              <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">
                Conversations ({conversations.length})
              </p>
              <button
                type="button"
                onClick={handleNewConversation}
                className="rounded-sm border border-navy-700 px-2 py-1 text-[10px] text-steel-500 hover:bg-navy-900"
              >
                Nouvelle
              </button>
            </div>
            <div className="hmi-scrollbar max-h-32 space-y-1 overflow-auto">
              {conversations.length ? (
                conversations.map((conv) => (
                  <button
                    key={conv.sessionId}
                    type="button"
                    onClick={() => void handleOpenConversation(conv.sessionId)}
                    disabled={conversationLoading}
                    className={`w-full rounded-sm border px-2 py-1 text-left text-[10px] transition ${
                      activeSessionId === conv.sessionId
                        ? "border-plant-accent/40 bg-plant-accent/10 text-steel-300"
                        : "border-navy-800 bg-navy-950/60 text-steel-500 hover:bg-navy-900"
                    }`}
                    title={conv.sessionId}
                  >
                    <p className="truncate font-mono">{conv.sessionId}</p>
                    <p className="truncate">{conv.preview || "Conversation"}</p>
                  </button>
                ))
              ) : (
                <p className="text-[10px] text-steel-600">Aucune conversation trouvée.</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">
              Long-term outputs ({longHistory.length})
            </p>
            <div className="hmi-scrollbar max-h-28 space-y-1 overflow-auto">
              {longHistory.length ? (
                longHistory.map((item) => (
                  <div key={item.id} className="rounded-sm border border-navy-800 bg-navy-950/60 px-2 py-1">
                    <p className="truncate font-mono text-[10px] text-steel-400">{item.memory_key}</p>
                    <p className="max-h-8 overflow-hidden text-[10px] text-steel-500">
                      {(item.memory_value || "").replace(/\n/g, " ")}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-[10px] text-steel-600">Aucun output enregistré.</p>
              )}
            </div>
          </div>

          <div className="mt-3 space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">
              Short-term session ({shortHistory.length})
            </p>
            <div className="hmi-scrollbar max-h-28 space-y-1 overflow-auto">
              {shortHistory.length ? (
                shortHistory.map((item) => (
                  <div key={item.id} className="rounded-sm border border-navy-800 bg-navy-950/60 px-2 py-1">
                    <p className="font-mono text-[10px] text-steel-400">
                      #{item.turn_index} · {item.role}
                    </p>
                    <p className="max-h-8 overflow-hidden text-[10px] text-steel-500">
                      {(item.content || "").replace(/\n/g, " ")}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-[10px] text-steel-600">Aucun échange session.</p>
              )}
            </div>
          </div>
        </div>

        {lastResponse ? (
          <dl className="space-y-1 text-xs text-steel-500">
            <div className="flex justify-between gap-2">
              <dt>Route</dt>
              <dd className="font-mono text-steel-300">{lastResponse.route_intent || "—"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Classification</dt>
              <dd className="font-mono text-steel-300">{lastResponse.statut_classification}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Production appliquée</dt>
              <dd className="font-mono text-steel-300">
                {lastResponse.production_applied ? "oui" : "non"}
              </dd>
            </div>
          </dl>
        ) : null}
      </aside>
    </div>
  );
}
