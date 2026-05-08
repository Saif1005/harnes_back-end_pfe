import type { ReactNode } from "react";

type Variant = "default" | "accent" | "warn";

const variantBorder: Record<Variant, string> = {
  default: "border-navy-700/80",
  accent: "border-plant-accent/40 shadow-[0_0_40px_-10px_rgba(34,211,238,0.25)]",
  warn: "border-alert-orange/35",
};

export function IndustrialPanel({
  title,
  subtitle,
  eyebrow,
  variant = "default",
  children,
  className = "",
  noPadding,
}: {
  title?: string;
  subtitle?: string;
  eyebrow?: string;
  variant?: Variant;
  children: ReactNode;
  className?: string;
  noPadding?: boolean;
}) {
  return (
    <section
      className={`relative overflow-hidden rounded-sm border bg-gradient-to-br from-navy-900/95 to-navy-950/90 ${variantBorder[variant]} ${className}`}
    >
      {/* Coins type plaque / armoire */}
      <span className="pointer-events-none absolute left-0 top-0 z-10 h-4 w-4 border-l-2 border-t-2 border-plant-accent/70" aria-hidden />
      <span className="pointer-events-none absolute right-0 top-0 z-10 h-4 w-4 border-r-2 border-t-2 border-plant-accent/40" aria-hidden />
      <span className="pointer-events-none absolute bottom-0 left-0 z-10 h-4 w-4 border-b-2 border-l-2 border-steel-700/80" aria-hidden />
      <span className="pointer-events-none absolute bottom-0 right-0 z-10 h-4 w-4 border-b-2 border-r-2 border-steel-700/80" aria-hidden />

      {/* Fond grille locale */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage: `linear-gradient(rgba(14,116,144,0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(14,116,144,0.06) 1px, transparent 1px)`,
          backgroundSize: "20px 20px",
        }}
        aria-hidden
      />

      {(title || eyebrow) && (
        <header className="relative border-b border-navy-800/90 bg-navy-950/50 px-4 py-3">
          {eyebrow ? (
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-plant-accent/90">{eyebrow}</p>
          ) : null}
          {title ? <h2 className="text-lg font-semibold tracking-tight text-steel-200">{title}</h2> : null}
          {subtitle ? <p className="mt-0.5 text-xs text-steel-600">{subtitle}</p> : null}
        </header>
      )}

      <div className={`relative ${noPadding ? "" : "p-4"}`}>{children}</div>
    </section>
  );
}

/** Bandeau compact type étiquette machine */
export function HmiTag({
  children,
  tone = "cyan",
}: {
  children: ReactNode;
  tone?: "cyan" | "orange" | "muted";
}) {
  const tones = {
    cyan: "border-plant-accent/40 bg-plant-accent/10 text-plant-glow",
    orange: "border-alert-orange/40 bg-alert-orange/10 text-alert-orange",
    muted: "border-navy-700 bg-navy-900 text-steel-500",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
