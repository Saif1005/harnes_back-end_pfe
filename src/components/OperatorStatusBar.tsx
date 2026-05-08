import { useEffect, useState } from "react";

function Led({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-steel-500">
      <span
        className={`h-2 w-2 rounded-full shadow-[0_0_8px_currentColor] ${ok ? "bg-emerald-500 text-emerald-400" : "bg-alert-red text-alert-red"}`}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function OperatorStatusBar() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const ts = now.toISOString().replace("T", " ").slice(0, 19);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-navy-800 bg-[linear-gradient(180deg,rgba(10,22,40,0.95)_0%,rgba(5,11,20,0.98)_100%)] px-5 py-2.5">
      <div className="flex flex-wrap items-center gap-4">
        <span className="font-mono text-[11px] text-plant-glow/90">
          UTC / SYS{" "}
          <time dateTime={now.toISOString()} className="text-steel-300">
            {ts}
          </time>
        </span>
        <div className="hidden h-4 w-px bg-navy-700 sm:block" aria-hidden />
        <div className="flex flex-wrap gap-4">
          <Led ok label="HMI" />
          <Led ok label="API" />
          <Led ok label="MES" />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="rounded-sm border border-navy-700 bg-navy-950 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-steel-500">
          Zone EU-WEST-3
        </span>
        <span className="rounded-sm border border-plant-accent/30 bg-plant-accent/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-plant-glow">
          Prod
        </span>
      </div>
    </div>
  );
}
