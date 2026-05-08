import { Cpu, Filter, Sparkles } from "lucide-react";
import type { RouteIntent } from "@/lib/intentFromPrompt";
import { detectIntentFromPrompt, intentLabel } from "@/lib/intentFromPrompt";

export type ToolMode = "auto" | RouteIntent;

const modes: { id: ToolMode; label: string; short: string }[] = [
  { id: "auto", label: "Auto (détection)", short: "Auto" },
  { id: "classification", label: "Classification MP/CHIMIE", short: "Classif." },
  { id: "workflow", label: "Workflow complet", short: "Workflow" },
  { id: "recette", label: "Recette", short: "Recette" },
  { id: "human", label: "Aide générale", short: "Général" },
];

interface PromptToolStripProps {
  draftText: string;
  toolMode: ToolMode;
  onToolModeChange: (mode: ToolMode) => void;
}

export function PromptToolStrip({
  draftText,
  toolMode,
  onToolModeChange,
}: PromptToolStripProps) {
  const detected = detectIntentFromPrompt(draftText);

  return (
    <div className="relative overflow-hidden border-b border-navy-800 bg-gradient-to-r from-navy-950/90 via-navy-900/80 to-navy-950/90 px-4 py-3">
      <div className="pointer-events-none absolute inset-y-0 left-0 w-px bg-gradient-to-b from-transparent via-plant-accent/40 to-transparent" aria-hidden />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-steel-500">
            <Filter className="h-3.5 w-3.5 text-plant-accent" />
            Routage outil
          </span>
          <div className="flex flex-wrap gap-1 rounded-sm border border-navy-700 bg-navy-950/80 p-1 shadow-inner">
            {modes.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => onToolModeChange(m.id)}
                className={[
                  "rounded-sm px-3 py-1.5 font-mono text-[11px] font-medium uppercase tracking-wide transition-all",
                  toolMode === m.id
                    ? "bg-plant-accent text-navy-950 shadow-[0_0_16px_-4px_rgba(34,211,238,0.6)]"
                    : "text-steel-500 hover:bg-navy-800 hover:text-steel-300",
                ].join(" ")}
                title={m.label}
              >
                {m.short}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-steel-600">
          <Cpu className="h-3.5 w-3.5 text-steel-600" />
          Pré-routeur local
        </div>
      </div>

      <div className="mt-3 rounded-sm border border-navy-800/80 bg-navy-950/50 px-3 py-2">
        {toolMode === "auto" && draftText.trim() ? (
          <p className="flex items-start gap-2 text-[11px] leading-relaxed text-steel-500">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-plant-accent" />
            {detected ? (
              <>
                Détection :{" "}
                <span className="font-semibold text-plant-glow">{intentLabel(detected)}</span>
                <span className="text-steel-600">
                  {" "}
                  — envoyé comme <code className="text-steel-400">preferred_route</code> si le backend le
                  supporte.
                </span>
              </>
            ) : (
              <span className="text-steel-600">
                Aucun motif fort : le routeur LLM du cerveau choisit la voie (classification / recette /
                général).
              </span>
            )}
          </p>
        ) : toolMode !== "auto" ? (
          <p className="text-[11px] leading-relaxed text-alert-orange/95">
            <span className="font-mono uppercase tracking-wider">Mode forcé</span> —{" "}
            <strong>{intentLabel(toolMode)}</strong> : la prochaine requête court-circuite le routeur
            Mistral.
          </p>
        ) : (
          <p className="text-[11px] text-steel-600">
            Saisissez une consigne : type &quot;classer&quot;, &quot;MP ou PDR&quot;, &quot;recette&quot;,
            tonnage… Le bandeau détectera la route.
          </p>
        )}
      </div>
    </div>
  );
}

export function resolvePreferredRoute(
  toolMode: ToolMode,
  question: string
): "classification" | "recette" | "workflow" | "human" | undefined {
  if (toolMode !== "auto") return toolMode;
  const d = detectIntentFromPrompt(question);
  return d ?? undefined;
}
