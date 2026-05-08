export function IndustrialLoader({ label = "Traitement en cours…" }: { label?: string }) {
  return (
    <div
      className="relative flex flex-col items-center justify-center gap-5 py-10"
      role="status"
      aria-live="polite"
    >
      <div className="relative flex h-16 w-16 items-center justify-center">
        <div
          className="absolute inset-0 animate-pulse-border rounded-full border-2 border-plant-accent/40"
          aria-hidden
        />
        <div className="absolute inset-2 rounded-full border border-navy-700 bg-navy-950/90" aria-hidden />
        <div className="relative flex h-9 w-9 items-end justify-center gap-1">
          {[0, 1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className="w-1 rounded-[1px] bg-gradient-to-t from-plant-accent to-plant-glow shadow-[0_0_12px_rgba(34,211,238,0.6)]"
              style={{
                height: `${10 + (i % 4) * 6}px`,
                animation: "barPulse 0.9s ease-in-out infinite",
                animationDelay: `${i * 100}ms`,
              }}
            />
          ))}
        </div>
      </div>
      <div className="text-center">
        <p className="font-mono text-[10px] uppercase tracking-[0.35em] text-steel-600">Orchestrateur</p>
        <p className="mt-1 font-mono text-xs text-steel-400">{label}</p>
      </div>
      <style>{`
        @keyframes barPulse {
          0%, 100% { opacity: 0.35; transform: scaleY(0.85); }
          50% { opacity: 1; transform: scaleY(1); }
        }
      `}</style>
    </div>
  );
}
