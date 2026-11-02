// Pravděpodobnosti s počtem pozorování a 95% intervalem spolehlivosti (Wilson) — statistická
// poctivost: holé procento bez n a intervalu je zavádějící. „coin“ = interval obsahuje 50 %,
// tj. výsledek se neliší od hodu mincí.

export interface P { pct: number | null; k: number; n: number; ci: [number, number] | null; coin: boolean }

export const cz = (v: number | null | undefined, d = 1) =>
  v == null ? "—" : v.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d });

/** Wilsonův interval z procenta a n (pro starší statistiky, které interval neposílají). */
export function wilson(pct: number, n: number): [number, number] | null {
  if (!n) return null;
  const z = 1.96, p = pct / 100, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.round(Math.max(0, c - h) * 1000) / 10, Math.round(Math.min(1, c + h) * 1000) / 10];
}

export function ciText(ci: [number, number] | null | undefined) {
  return ci ? `${cz(ci[0])}–${cz(ci[1])} %` : "";
}

/** „62,3 %“ + malým písmem interval a n; šedě a s poznámkou, když jde o hod mincí (binární jev). */
export function Prob({ p, binary = false, big = false }: { p?: P | null; binary?: boolean; big?: boolean }) {
  if (!p || p.pct == null) return <span className="text-gray-600">—</span>;
  const coin = binary && p.coin;
  const few = p.n < 30;
  return (
    <span className="whitespace-nowrap" title={`${p.k} z ${p.n} · 95% interval ${ciText(p.ci)}${coin ? " · neliší se od 50 %" : ""}`}>
      <span className={`${big ? "text-lg" : ""} font-semibold ${coin || few ? "text-gray-400" : "text-white"}`}>{cz(p.pct)} %</span>
      <span className="ml-1 text-[10px] text-gray-500">({ciText(p.ci)}, n={p.n})</span>
      {coin && <span className="ml-1 text-[10px] text-yellow-500/80">≈ náhoda</span>}
      {few && !coin && <span className="ml-1 text-[10px] text-yellow-500/80">málo dat</span>}
    </span>
  );
}

/** Vodorovný pruh s vyznačeným intervalem spolehlivosti. */
export function ProbBar({ label, p, accent = "#3b82f6", binary = false }: { label: string; p?: P | null; accent?: string; binary?: boolean }) {
  const v = p?.pct ?? 0;
  const ci = p?.ci;
  return (
    <div className="text-xs">
      <div className="flex items-center gap-2">
        <span className="w-40 shrink-0 text-gray-400 truncate" title={label}>{label}</span>
        <div className="relative flex-1 h-2 rounded-full bg-[#232735] overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${Math.max(1, v)}%`, background: binary && p?.coin ? "#64748b" : accent }} />
          {ci && <div className="absolute top-0 h-full bg-white/25" style={{ left: `${ci[0]}%`, width: `${Math.max(0.5, ci[1] - ci[0])}%` }} />}
          {binary && <div className="absolute top-[-2px] h-3 w-px bg-yellow-500/60" style={{ left: "50%" }} />}
        </div>
      </div>
      <div className="mt-0.5 pl-[168px]"><Prob p={p} binary={binary} /></div>
    </div>
  );
}

export const clock = (openH: number, minutes: number) => {
  const t = Math.round(openH * 60 + minutes);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};
