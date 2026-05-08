/**
 * Détection légère (regex / mots-clés FR) pour proposer ou forcer une route
 * alignée sur le graphe backend : classification | recette | human.
 */

export type RouteIntent = "classification" | "recette" | "workflow" | "human";

export type DetectedIntent = RouteIntent | null;

/** Mots-clés / motifs orientés classification MP/PDR (API backend classification). */
const CLASSIFICATION_HINTS: RegExp[] = [
  /\bclass(er|ification|ifiez|ifions|ée|ées)\b/i,
  /\btypolog(ie|ier)\b/i,
  /\bcat[ée]goris(er|ation)\b/i,
  /\b(mp|pdr)\b.*\b(ou|vs|versus|et)\b.*\b(mp|pdr)\b/i,
  /\b(est|sont)[- ]ce\b.*\b(mp|pdr|matière)\b/i,
  /\bmati[eè]re\s+premi[eè]re\b/i,
  /\bpi[eè]ce\s+de\s+rechange\b/i,
  /\bmagasin\b.*\b(mp|pdr|chimie)\b/i,
  /\b(niveau|type)\s+1\b/i,
];

/** Recette / tonnage → nœud recette + agent recette backend. */
const RECETTE_HINTS: RegExp[] = [
  /\brecette\b/i,
  /\btonn(age|es?)\b/i,
  /\b\d+[\s,.]*\d*\s*(t|tonne|tonnes|kg)\b/i,
  /\bdosage\b/i,
  /\bratio\b/i,
  /\bprépar(er|e)\b.*\b(production|ligne)\b/i,
];

/** Sujets hors périmètre atelier → route human (aligné heuristique backend). */
const HUMAN_HINTS: RegExp[] = [
  /\b(commande|commander|fournisseur|acheter|achats?)\b/i,
];

export function detectIntentFromPrompt(text: string): DetectedIntent {
  const t = (text || "").trim();
  if (!t) return null;

  const hasClassHint = CLASSIFICATION_HINTS.some((re) => re.test(t));
  const hasRecetteHint = RECETTE_HINTS.some((re) => re.test(t));
  const asksExplicitWorkflow = /\bworkflow\b|\bcomplet\b/i.test(t);
  const asksExplicitClassificationList =
    /\bclass(er|e|ification)\b/i.test(t) && /[:,-]/.test(t);
  if (asksExplicitWorkflow && hasClassHint && hasRecetteHint) return "workflow";
  if (asksExplicitClassificationList) return "classification";

  for (const re of HUMAN_HINTS) {
    if (re.test(t)) return "human";
  }
  for (const re of CLASSIFICATION_HINTS) {
    if (re.test(t)) return "classification";
  }
  for (const re of RECETTE_HINTS) {
    if (re.test(t)) return "recette";
  }
  return null;
}

export function intentLabel(intent: RouteIntent): string {
  switch (intent) {
    case "classification":
      return "Classification MP/CHIMIE";
    case "recette":
      return "Recette production";
    case "workflow":
      return "Workflow complet";
    case "human":
      return "Réponse générale";
    default:
      return "";
  }
}
