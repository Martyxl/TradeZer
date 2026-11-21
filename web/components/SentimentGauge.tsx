"use client";

import { Gauge } from "lucide-react";
import { useRegime, type Regime } from "@/components/RegimeCard";

interface Part { key: string; label: string; hint: string; value: number }
interface Hist { next_day_move?: number; up: number; fwd20: number; pos20: number; p10_20?: number }
export interface Sentiment {
  score: number; band: string; label: string; parts: Part[]; as_of_date: string;
  vix: number; vix_term: number; backwardation: boolean; history: Hist; history_all: Hist;
  history_period?: string;
}

// Pásma 0–20 / 20–40 / 40–60 / 60–80 / 80–100 (stejně jako backend).
const ZONES = [
  { to: 20, color: "#ef4444" }, { to: 40, color: "#f97316" }, { to: 60, color: "#94a3b8" },
  { to: 80, color: "#84cc16" }, { to: 100, color: "#22c55e" },
];
const colorOf = (v: number) => (ZONES.find((z) => v < z.to) ?? ZONES[4]).color;
const fmt = (v: number, d = 1) => v.toLocaleString("cs-CZ", { minimumFractionDigits: d, maximumFractionDigits: d });

/** Půlkruhový tachometr 0–100 (0 vlevo = strach, 100 vpravo = chamtivost). */
function Dial({ score }: { score: number }) {
  const W = 220, cx = 110, cy = 108, r = 88, sw = 14;
  const pt = (v: number, rad = r) => {
    const a = Math.PI * (1 - v / 100);
    return { x: cx + rad * Math.cos(a), y: cy - rad * Math.sin(a) };
  };
  const arc = (a: number, b: number) => {
    const p = pt(a), q = pt(b);
    return `M ${p.x} ${p.y} A ${r} ${r} 0 0 1 ${q.x} ${q.y}`;
  };
  let from = 0;
  const tip = pt(score, r - 22);
  return (
    <svg viewBox={`0 0 ${W} 122`} className="w-full max-w-[240px]" role="img"
         aria-label={`Sentiment ${score} ze 100`}>
      {ZONES.map((z) => {
        const d = arc(from + 0.8, z.to - 0.8);
        from = z.to;
        return <path key={z.to} d={d} stroke={z.color} strokeWidth={sw} fill="none" opacity={0.85} />;
      })}
      <line x1={cx} y1={cy} x2={tip.x} y2={tip.y} stroke="rgb(var(--tz-ink))" strokeWidth={3} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={6} fill="rgb(var(--tz-ink))" />
      <text x={pt(0).x} y={cy + 14} fontSize={9} fill="#9ca3af" textAnchor="middle">0</text>
      <text x={pt(100).x} y={cy + 14} fontSize={9} fill="#9ca3af" textAnchor="middle">100</text>
    </svg>
  );
}

function Takeaways({ s }: { s: Sentiment }) {
  const h = s.history, all = s.history_all;
  const move = h.next_day_move;
  return (
    <ul className="mt-3 space-y-1.5 text-[12px] leading-snug text-gray-300">
      {move != null && (
        <li>
          <span className="font-semibold text-white">Daytrading:</span>{" "}
          {move >= 1.2
            ? <>další den se Nasdaq historicky hýbe v průměru <b>{fmt(move)}× víc</b> než obvykle. Menší pozice, širší stop.</>
            : move <= 0.8
              ? <>další den bývá klidnější (pohyb {fmt(move)}× běžného). Menší rozsahy, méně prostoru pro cíle.</>
              : <>velikost pohybu kolem normálu ({fmt(move)}× běžného dne).</>}
        </li>
      )}
      <li>
        <span className="font-semibold text-white">Směr dne:</span>{" "}
        signál to není. Nahoru šlo {h.up} % dní (běžně {all.up} %).
      </li>
      <li>
        <span className="font-semibold text-white">Na 20 dní:</span>{" "}
        Nasdaq v průměru {h.fwd20 >= 0 ? "+" : ""}{fmt(h.fwd20)} % (běžně +{fmt(all.fwd20)} %), kladný v {h.pos20} % případů
        {h.p10_20 != null && <>, ale v 1 z 10 případů horší než {fmt(h.p10_20)} %</>}.
      </li>
      {s.backwardation && (
        <li className="text-[#ff8f8f]">
          VIX je nad tříměsíčním VIX3M ({fmt(s.vix_term, 2)}): trh čeká největší nervozitu teď, ne později.
        </li>
      )}
    </ul>
  );
}

export function SentimentCard({ regime }: { regime?: Regime | null }) {
  const fetched = useRegime(true);
  const s = ((regime ?? fetched) as (Regime & { sentiment?: Sentiment }) | null)?.sentiment;
  if (!s) return null;
  const c = colorOf(s.score);
  return (
    <div className="rounded-2xl border border-line bg-panel p-4">
      <div className="flex items-center gap-2">
        <Gauge size={15} className="text-blue-400" />
        <h2 className="text-sm font-semibold text-white">Sentiment trhu</h2>
        <span className="ml-auto text-[10px] text-gray-500">VIX {fmt(s.vix, 1)} · {new Date(s.as_of_date).toLocaleDateString("cs-CZ")}</span>
      </div>

      <div className="mt-2 flex flex-col items-center">
        <Dial score={s.score} />
        <div className="-mt-1 text-center">
          <div className="text-3xl font-bold tabular-nums" style={{ color: c }}>{s.score}</div>
          <div className="text-sm font-semibold" style={{ color: c }}>{s.label}</div>
        </div>
      </div>

      <div className="mt-3 space-y-1.5">
        {s.parts.map((p) => (
          <div key={p.key} title={p.hint} className="grid grid-cols-[1fr_88px_24px] items-center gap-2 text-[11px]">
            <span className="truncate text-gray-400">{p.label}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-gray-500/20">
              <div className="h-full rounded-full" style={{ width: `${Math.max(p.value, 3)}%`, background: colorOf(p.value) }} />
            </div>
            <span className="text-right tabular-nums text-gray-300">{p.value}</span>
          </div>
        ))}
      </div>

      <Takeaways s={s} />

      <p className="mt-3 text-[10px] leading-snug text-gray-600">
        Každá složka = kde je dnešní hodnota v rozpětí posledního roku (0 = nejvíc strachu). Dopady: historie
        Nasdaq-100 {s.history_period ?? "2011-11 – 2026-11"}, přepočet jednou týdně. Není to investiční doporučení.
      </p>
    </div>
  );
}
