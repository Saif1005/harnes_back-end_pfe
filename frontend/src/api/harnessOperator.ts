/**
 * Pilotage orchestrateur Harness (/invoke + /resume) avec mapping minimal
 * vers `AskAgentResponse` pour réutiliser l’UI Assistant existante.
 */
import { harnessModeEnabled, createHarnessAxios } from "@/api/harnessClient";
import { postAskAgent } from "@/api/askAgent";
import type { AskAgentPayload, AskAgentResponse, StockAlert } from "@/types/askAgent";

const H_TOKEN = "harness:";

interface HarnessEnvelope {
  run_id?: string;
  status?: string;
  route?: string;
  message?: string;
  approval_id?: string;
  details?: {
    tool_results?: Array<Record<string, unknown>>;
    metadata?: Record<string, unknown>;
    errors?: unknown[];
    react_trace?: unknown[];
  };
}

function enc(b: string): string {
  try {
    return btoa(b);
  } catch {
    return "";
  }
}

function dec(b: string): string {
  try {
    return atob(b);
  } catch {
    return "";
  }
}

/** Jeton opaque pour `/resume` (évite collisions avec ancien JWT cerveau). */
export function buildHarnessApprovalToken(runId: string, approvalId: string): string {
  return H_TOKEN + enc(JSON.stringify({ run_id: runId, approval_id: approvalId }));
}

export function parseHarnessApprovalToken(token: string): { run_id: string; approval_id: string } | null {
  if (!token?.startsWith(H_TOKEN)) return null;
  const payload = dec(token.slice(H_TOKEN.length));
  try {
    const o = JSON.parse(payload) as { run_id?: string; approval_id?: string };
    if (o.run_id && o.approval_id) return { run_id: o.run_id, approval_id: o.approval_id };
  } catch {
    /* ignore */
  }
  return null;
}

function firstRecipeComputeRows(envelope: HarnessEnvelope): AskAgentResponse["recipe_items"] {
  const tr = envelope.details?.tool_results || [];
  for (const row of tr) {
    if (String(row.tool_name || "") !== "recipe_compute") continue;
    if (!row.ok) continue;
    const data = row.data as { recipe_items?: AskAgentResponse["recipe_items"] } | undefined;
    if (Array.isArray(data?.recipe_items) && data!.recipe_items!.length)
      return data!.recipe_items;
  }
  return undefined;
}

function lastPredictionEnvelope(envelope: HarnessEnvelope): AskAgentResponse["stock_prediction"] {
  const tr = envelope.details?.tool_results || [];
  for (let i = tr.length - 1; i >= 0; i--) {
    const row = tr[i];
    if (String(row.tool_name || "") !== "prediction_regression") continue;
    if (!row.ok) continue;
    const data = row.data as Record<string, unknown> | undefined;
    if (!data) continue;
    return {
      model: typeof data.model_used === "string" ? data.model_used : undefined,
      predicted_totals_kg:
        typeof data.forecast_next_kg === "object" && data.forecast_next_kg !== null
          ? (data.forecast_next_kg as NonNullable<
              NonNullable<AskAgentResponse["stock_prediction"]>["predicted_totals_kg"]
            >)
          : undefined,
    } as AskAgentResponse["stock_prediction"];
  }
  return undefined;
}

function persistEcho(payload: AskAgentPayload, response: AskAgentResponse): void {
  try {
    localStorage.setItem(
      "sotipapier_last_ask_agent",
      JSON.stringify({
        at: new Date().toISOString(),
        payload,
        response,
      })
    );
    window.dispatchEvent(new Event("sotipapier:ask-agent-updated"));
  } catch {
    /* private mode / quota */
  }
}

function mapHarnessToAskAgent(env: HarnessEnvelope): AskAgentResponse {
  const meta = env.details?.metadata || {};
  const alerts = meta.stock_alerts as StockAlert[] | undefined;
  const capacity = meta.production_capacity as AskAgentResponse["production_capacity"];
  const status = env.status || "";
  const msg = String(env.message || "").trim();
  const needHitl = status === "interrupted" && Boolean(env.approval_id && env.run_id);
  const token = needHitl && env.run_id && env.approval_id ? buildHarnessApprovalToken(env.run_id, env.approval_id) : "";

  const recipeFromTools = firstRecipeComputeRows(env);
  const predicted = lastPredictionEnvelope(env);

  return {
    id_article_erp: "HARNESS",
    route_intent: env.route?.includes("recette") ? "recette" : env.route?.includes("orchestrator") ? "workflow" : undefined,
    statut_classification: "HARNESS",
    categorie_cible: "CHAINE_INDUSTRIELLE",
    resultat_agent_brut: msg,
    stock_alerts: Array.isArray(alerts) ? alerts : [],
    recipe_items: recipeFromTools || [],
    production_capacity: capacity,
    stock_prediction: predicted,
    final_response: msg,
    reponse_agent: msg,
    confirmation_required: needHitl,
    confirmation_token: token,
    production_applied:
      typeof meta.stock_consumption === "object" &&
      meta.stock_consumption !== null &&
      Number((meta.stock_consumption as { count?: number }).count || 0) > 0,
  };
}

export async function invokeHarnessMapped(payload: AskAgentPayload): Promise<AskAgentResponse> {
  const client = createHarnessAxios();
  const { data } = await client.post<HarnessEnvelope>("/invoke", {
    session_id: payload.session_id || "",
    user_id: "operator-ui",
    query: payload.question_operateur,
    source: "user",
  });
  return mapHarnessToAskAgent(data);
}

export async function resumeHarnessMapped(runId: string, approvalId: string, approved: boolean): Promise<AskAgentResponse> {
  const client = createHarnessAxios();
  const { data } = await client.post<HarnessEnvelope>("/resume", {
    run_id: runId,
    approval_id: approvalId,
    approved,
    reviewer: "operator-ui",
    comment: approved ? "Approved from Sotipapier UI" : "Rejected",
  });
  return mapHarnessToAskAgent(data);
}

/**
 * Point d’entrée unique depuis l’Assistant : cerveau classique OU Harness selon `.env`.
 */
export async function submitOperatorTurn(payload: AskAgentPayload): Promise<AskAgentResponse> {
  if (!harnessModeEnabled()) {
    return postAskAgent(payload);
  }

  let data: AskAgentResponse;
  if (payload.confirm_production && payload.confirmation_token) {
    const p = parseHarnessApprovalToken(payload.confirmation_token);
    if (p) {
      data = await resumeHarnessMapped(p.run_id, p.approval_id, true);
      persistEcho(payload, data);
      return data;
    }
  }

  data = await invokeHarnessMapped(payload);
  persistEcho(payload, data);
  return data;
}
