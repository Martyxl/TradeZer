"use client";

import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown, MoveRight, Target, HelpCircle } from "lucide-react";
import { dashFetch } from "@/lib/dashboardData";
import { useAuth } from "@/lib/auth";

interface BiasSnapshot {
  prob_down: number; prob_neutral: number; prob_up: number;
  direction: string; trust_score: number; n_news: number;
  snapshot_at: string;
  realized_direction: string | null; realized_pct: number | null;
  ny_realized_direction?: string | null; ny_realized_pct?: number | null;
  v2_direction?: string | null; v2_cats?: string | null;
}
interface BiasLive {
  prob_down: number; prob_neutral: number; prob_up: number;
  direction: string; trust_score: number; n_news: number;
}
interface BiasToday {
  ticker: string; date: string;
  snapshot: BiasSnapshot | null; live: BiasLive;
}
interface Track { k: number; n: number; pct: number | null; ci: [number, number] | null; coin: boolean }
interface BiasStats {
  track?: { since: string | null; ny: Track; london: Track;
            v2: { ny: Track; london: Track; signal_days: number; days: number } };
  total: number; accuracy: number | null;
  directional_total: number; directional_accuracy: number | null;
  directional_total_london?: number;
}
interface GammaLite {
  underlying: string; regime: "positive" | "negative";
  flip: number | null; net_gex: number;
}

const DIR_META: Record<string, { label: string; color: string; Icon: typeof TrendingUp }> = {
  up: { label: "LONG", color: "#4ade80", Icon: TrendingUp },
  down: { label: "SHORT", color: "#f87171", Icon: TrendingDown },
  neutral: { label: "NEUTRAL", color: "#eab308", Icon: MoveRight },
  unknown: { label: "NELZE URČIT", color: "#94a3b8", Icon: HelpCircle },
};

const ci = (t: Track) => (t.ci ? `${t.ci[0].toFixed(0)}–${t.ci[1].toFixed(0)} %` : "");

/** Historická úspěšnost s intervalem (nahradila trust score, které s úspěšností nesouviselo). */
function trackLabel(t?: Track): { text: string; color: string; title: string } | null {
  if (!t || !t.n) return null;
  const title = `${t.k} z ${t.n} směrových dní, 95% interval ${ci(t)}`;
  if (t.n < 20) return { text: `historicky ${t.pct?.toFixed(0)} % · málo dat (${t.n} dní)`, color: "#94a3b8", title };
  if (t.coin) return { text: `historicky ${t.pct?.toFixed(0)} % · ≈ náhoda`, color: "#eab308", title };
  return { text: `historicky ${t.pct?.toFixed(0)} % (${ci(t)})`, color: (t.pct ?? 0) > 50 ? "#4ade80" : "#f87171", title };
}

function ProbRow({ b }: { b: { prob_down: number; prob_neutral: number; prob_up: number } }) {
  return (
    <div className="flex h-2.5 rounded-full overflow-hidden bg-[#232735]">
      <div style={{ width: `${b.prob_down * 100}%`, background: "#f87171" }} />
      <div style={{ width: `${b.prob_neutral * 100}%`, background: "#64748b" }} />
      <div style={{ width: `${b.prob_up * 100}%`, background: "#4ade80" }} />
    </div>
  );
}

export function BiasCard({ ticker }: { ticker: string }) {
  const [data, setData] = useState<BiasToday | null>(null);
  const [stats, setStats] = useState<BiasStats | null>(null);
  const [gamma, setGamma] = useState<GammaLite | null>(null);
  const { user } = useAuth();

  useEffect(() => {
    setData(null);
    setGamma(null);
    dashFetch(`/api/bias/today?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setData)
      .catch(() => {});
    dashFetch(`/api/bias/stats?ticker=${ticker}&days=30`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => {});
    // Gamma režim jako doplňkový kontext (tichá degradace, když nejsou data).
    dashFetch(`/api/gamma?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setGamma(j?.instrument ?? null))
      .catch(() => {});
  }, [ticker]);

  if (!data) return null;
  const snap = data.snapshot;
  const bias = snap ?? data.live;
  const meta = DIR_META[bias.direction] ?? DIR_META.neutral;
  const track = trackLabel(stats?.track?.ny);
  const { Icon } = meta;
  const isUnknown = bias.direction === "unknown";

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Target size={15} className="text-blue-400" />
          <h2 className="text-sm font-semibold text-white">Dnešní BIAS · {ticker}</h2>
          <span className="text-[10px] text-gray-500">
            {snap ? `snapshot London open (${bias.n_news} zpráv)` : `průběžný (${bias.n_news} zpráv) — snapshot v 9:00`}
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2 rounded-lg px-3 py-1.5 border"
             style={{ borderColor: meta.color + "55", background: meta.color + "14" }}>
          <Icon size={16} style={{ color: meta.color }} />
          <span className="text-sm font-bold" style={{ color: meta.color }}>{meta.label}</span>
          {!isUnknown && track && (
            <span className="text-[10px]" style={{ color: track.color }} title={track.title}>· {track.text}</span>
          )}
        </div>
      </div>

      {isUnknown ? (
        <p className="mt-3 text-[11px] text-gray-400">
          Na základě aktuální situace <strong>nelze určit směr</strong> — chybí důvěryhodné predikce
          (žádné relevantní zprávy s nenulovou confidence). Není to plochý trh (neutral), ale absence
          podkladu pro směrovou sázku.
        </p>
      ) : (
        <div className="mt-3">
          <ProbRow b={bias} />
          <div className="mt-1 flex justify-between text-[10px] text-gray-500">
            <span className="text-red-400">↓ {(bias.prob_down * 100).toFixed(0)}%</span>
            <span>→ {(bias.prob_neutral * 100).toFixed(0)}%</span>
            <span className="text-green-400">↑ {(bias.prob_up * 100).toFixed(0)}%</span>
          </div>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500">
        {snap?.ny_realized_direction && (
          <span title="Pohyb v NY session 9:30–16:00 ET (bez premarketu / gapu)">
            Realita NY session:{" "}
            <span style={{ color: DIR_META[snap.ny_realized_direction]?.color }}>
              {DIR_META[snap.ny_realized_direction]?.label}
              {snap.ny_realized_pct != null && ` (${(snap.ny_realized_pct * 100).toFixed(2)} %)`}
            </span>
            {" — "}
            {snap.ny_realized_direction === snap.direction ? "✓ bias seděl" : "✗ bias neseděl"}
          </span>
        )}
        {stats && stats.total > 0 && (
          <span title="Měřeno na NY session (9:30–16:00 ET). Dřívější metrika London open → close v sobě měla i premarket/gap a úspěšnost zkreslovala.">
            Úspěšnost 30 dní (NY session): <span className="text-gray-300">{((stats.accuracy ?? 0) * 100).toFixed(0)} %</span>
            {stats.directional_total > 0 && (
              <> · směrové biasy: <span className="text-gray-300">
                {((stats.directional_accuracy ?? 0) * 100).toFixed(0)} %</span> ({stats.directional_total}×)</>
            )}
          </span>
        )}
        {stats?.track && stats.track.ny.n > 0 && (
          <span title="Celá historie, jen dny se směrovým biasem (LONG/SHORT) a směrovým pohybem NY session. Interval = 95% spolehlivost.">
            Celkem od {stats.track.since}: <span className="text-gray-300">{stats.track.ny.pct?.toFixed(0)} %</span>
            {" "}({ci(stats.track.ny)}, n={stats.track.ny.n}){stats.track.ny.coin && <span className="text-yellow-500/80"> · ≈ náhoda</span>}
          </span>
        )}
        {stats && stats.total === 0 && (
          <span>{stats.directional_total_london ? "Úspěšnost na NY session se právě dopočítává." : "Statistika úspěšnosti se začne tvořit od zítřka."}</span>
        )}
      </div>

      {user?.is_admin && stats?.track && (
        <div className="mt-2 rounded-lg border border-dashed border-[#2f3b55] px-2.5 py-1.5 text-[11px] text-gray-400">
          <span className="font-medium text-blue-300">Bias v2 (stín, jen admin):</span>{" "}
          dnes {snap?.v2_direction ? (DIR_META[snap.v2_direction]?.label ?? "bez signálu") : "—"}
          {snap?.v2_cats ? <span className="text-gray-500"> ({snap.v2_cats})</span> : null}
          {" · "}London→close {stats.track.v2.london.pct ?? "—"} % ({ci(stats.track.v2.london)}, n={stats.track.v2.london.n})
          {" · "}NY {stats.track.v2.ny.pct ?? "—"} % (n={stats.track.v2.ny.n})
          {" · "}signál {stats.track.v2.signal_days}/{stats.track.v2.days} dní
          <span className="text-gray-600"> · vs. současný London {stats.track.london.pct ?? "—"} % (n={stats.track.london.n})</span>
        </div>
      )}

      {gamma && (
        <div className="mt-2 flex items-start gap-2 rounded-lg border border-[#232735] bg-[#151823] px-2.5 py-1.5 text-[11px]">
          <span className="text-indigo-400 font-medium shrink-0">Gamma režim:</span>
          <span className="text-gray-400">
            <span
              className="font-semibold"
              style={{ color: gamma.regime === "positive" ? "#4ade80" : "#f87171" }}
            >
              {gamma.regime === "positive" ? "Pozitivní" : "Negativní"} ({gamma.underlying})
            </span>
            {gamma.regime === "positive"
              ? " → dealeři tlumí pohyby, trh spíš mean-revert/klidnější (výhodné pro fade extrémů)."
              : " → dealeři pohyby zesilují, trh trendový/volatilní (pozor na breakouty)."}
            {gamma.flip != null && (
              <span className="text-gray-500"> Flip {gamma.flip}.</span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
