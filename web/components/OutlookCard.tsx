"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarClock, TrendingUp, TrendingDown, Minus, Loader2, CheckCircle2, Clock } from "lucide-react";

interface Leg { dir: "up" | "down" | "flat"; text: string }
interface Stat { n: number; hits: number; hit_rate: number | null }
interface Scenario {
  title: string; time_utc: string; impact: string;
  forecast: string; previous: string; actual: string;
  category: string; realized: "hot" | "inline" | "cool" | null;
  released?: boolean; actual_source?: string | null;
  hot: Leg; inline: Leg; cool: Leg; stat?: Stat | null;
}
interface EventRow {
  title: string; impact: string; time_utc: string;
  forecast: string; previous: string; actual: string;
}
interface Outlook {
  ticker: string; date: string;
  events: EventRow[]; scenarios: Scenario[];
  bias: { direction: string; trust_score: number } | null;
  narrative: string;
}

// Očisti případný markdown z LLM narativu (starší cache může mít #, **).
const clean = (t: string) =>
  (t || "")
    .replace(/^#{1,6}\s+.*$/gm, "")   // řádky s nadpisem
    .replace(/\*\*(.*?)\*\*/g, "$1")  // **bold**
    .replace(/[*#]/g, "")
    .trim();

const cet = (iso: string) =>
  iso ? new Date(iso).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Prague" }) : "";

function DirTag({ leg }: { leg: Leg }) {
  const map = {
    up: { c: "#4ade80", Icon: TrendingUp },
    down: { c: "#f87171", Icon: TrendingDown },
    flat: { c: "#eab308", Icon: Minus },
  }[leg.dir];
  const Icon = map.Icon;
  return (
    <span className="inline-flex items-center gap-1" style={{ color: map.c }}>
      <Icon size={13} />
    </span>
  );
}

const BUCKET_WORD = { hot: "nad forecastem", inline: "v souladu s forecastem", cool: "pod forecastem" } as const;
const BUCKET_COLOR = { hot: "#fb923c", inline: "#eab308", cool: "#60a5fa" } as const;
const DIR_WORD = { up: "nahoru", down: "dolů", flat: "bez výrazného směru" } as const;
const DIR_COLOR = { up: "#4ade80", down: "#f87171", flat: "#eab308" } as const;

/** Stav eventu: čeká / vyšlo (+ hodnota) / vyšlo, ale čísla ještě nemáme. */
function StatusTag({ s }: { s: Scenario }) {
  if (s.realized) {
    return (
      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold"
            style={{ background: BUCKET_COLOR[s.realized] + "22", color: BUCKET_COLOR[s.realized] }}>
        <CheckCircle2 size={11} /> vyšlo · {BUCKET_WORD[s.realized]}
      </span>
    );
  }
  if (s.released) {
    return <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-300">vyšlo · čekám na čísla</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 rounded bg-[#1e2536] px-1.5 py-0.5 text-[10px] text-blue-300">
      <Clock size={11} /> čeká · {cet(s.time_utc)}
    </span>
  );
}

const SCEN_ROWS: { key: "hot" | "inline" | "cool"; label: string }[] = [
  { key: "hot", label: "🔥 Nad forecastem" },
  { key: "inline", label: "➖ V souladu" },
  { key: "cool", label: "❄️ Pod forecastem" },
];

export function OutlookCard({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Outlook | null>(null);
  const [loading, setLoading] = useState(true);
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback((silent: boolean) => {
    if (!silent) { setLoading(true); setD(null); }
    return fetch(`/api/bias/outlook?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j || !silent) setD(j); if (j) setUpdated(new Date()); })
      .catch(() => { if (!silent) setD(null); })
      .finally(() => { if (!silent) setLoading(false); });
  }, [ticker]);

  useEffect(() => { load(false); }, [load]);

  // Dokud má dnešek nevyhodnocené eventy, obnovuj každé 2 min — skutečná čísla dorazí pár minut po vydání.
  const pending = !!d?.scenarios.some((s) => !s.realized);
  useEffect(() => {
    if (!pending) return;
    const id = setInterval(() => { if (document.visibilityState === "visible") load(true); }, 120_000);
    return () => clearInterval(id);
  }, [pending, load]);

  const done = (d?.scenarios || []).filter((s) => s.realized || s.released);

  return (
    <div className="rounded-2xl border border-[#2a2d3a] bg-[#1a1d27] p-6">
      <div className="flex items-center gap-2 mb-3">
        <CalendarClock size={16} className="text-blue-400" />
        <h2 className="text-lg font-semibold text-white">Dnešní výhled — {ticker}</h2>
        {d?.date && (
          <span className="text-xs text-gray-500">
            {d.date} · {done.length ? `aktualizováno ${updated?.toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" }) ?? ""}` : "před openem"}
          </span>
        )}
      </div>

      {loading ? (
        <div className="flex h-24 items-center justify-center gap-2 text-gray-400">
          <Loader2 size={20} className="animate-spin text-blue-400" />
          <span className="text-xs">Sestavuji výhled…</span>
        </div>
      ) : !d ? (
        <p className="text-sm text-gray-500">Výhled se nepodařilo načíst.</p>
      ) : (
        <>
          {/* Co už dnes nastalo — skutečnost vydaných zpráv a co z ní plyne pro instrument */}
          {done.length > 0 && (
            <div className="mb-4 rounded-xl border border-blue-900/50 bg-blue-950/20 p-3">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-blue-300">Co dnes nastalo</div>
              <ul className="space-y-1.5">
                {done.map((s, i) => {
                  const leg = s.realized ? s[s.realized] : null;
                  return (
                    <li key={i} className="text-[13px] leading-snug text-gray-200">
                      <span className="text-gray-500">{cet(s.time_utc)}</span>{" "}
                      <span className="font-semibold text-white">{s.title}</span>{" "}
                      {s.realized && leg ? (
                        <>
                          <span className="font-semibold" style={{ color: BUCKET_COLOR[s.realized] }}>{s.actual}</span>
                          <span className="text-gray-500"> vs fc {s.forecast || "—"}</span>
                          {" → "}<span style={{ color: BUCKET_COLOR[s.realized] }}>{BUCKET_WORD[s.realized]}</span>
                          <div className="mt-0.5 flex items-start gap-1.5 pl-11 text-[12px] text-gray-300">
                            <DirTag leg={leg} />
                            <span>
                              {leg.text}{" "}
                              <span className="font-medium" style={{ color: DIR_COLOR[leg.dir] }}>
                                (typická reakce {d.ticker}: {DIR_WORD[leg.dir]})
                              </span>
                            </span>
                          </div>
                        </>
                      ) : (
                        <span className="text-gray-400">— vyšlo, skutečné číslo zatím nemáme (doplní se během pár minut)</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* LLM narativ dne */}
          {d.narrative && (
            <>
            {done.length > 0 && <div className="mb-1 text-[10px] uppercase tracking-wider text-gray-500">Ranní komentář (před zprávami)</div>}
            <p className="mb-4 whitespace-pre-line rounded-xl border border-[#2a2d3a] bg-[#0f1117] p-3 text-sm leading-relaxed text-gray-200">
              {clean(d.narrative)}
            </p>
            </>
          )}

          {/* Bias kontext */}
          {d.bias && (
            <div className="mb-4 text-xs text-gray-400">
              Aktuální bias:{" "}
              <span
                className="font-medium"
                style={{ color: d.bias.direction === "up" ? "#4ade80" : d.bias.direction === "down" ? "#f87171" : "#eab308" }}
              >
                {d.bias.direction === "up" ? "LONG" : d.bias.direction === "down" ? "SHORT" : d.bias.direction === "neutral" ? "NEUTRAL" : "—"}
              </span>{" "}
              <span className="text-gray-600">(trust {d.bias.trust_score})</span>
            </div>
          )}

          {d.scenarios.length === 0 ? (
            <p className="text-sm text-gray-500">
              Dnes nejsou naplánované žádné klíčové US eventy (high/medium) s vyhodnotitelným dopadem.
              Sleduj bias a širší kontext.
            </p>
          ) : (
            <div className="space-y-3">
              {d.scenarios.map((s, i) => (
                <div key={i} className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-white text-sm">{s.title}</span>
                    <span className="text-[10px] uppercase rounded px-1.5 py-0.5"
                          style={{ background: s.impact === "high" ? "#7f1d1d55" : "#78350f55",
                                   color: s.impact === "high" ? "#fca5a5" : "#fcd34d" }}>
                      {s.impact}
                    </span>
                    <span className="text-[11px] text-gray-500">{cet(s.time_utc)} CET</span>
                    <StatusTag s={s} />
                    <span className="text-[11px] text-gray-500">
                      fc {s.forecast || "—"} · prev {s.previous || "—"}
                      {s.actual ? <> · <span className="font-semibold" style={{ color: s.realized ? BUCKET_COLOR[s.realized] : "#d1d5db" }}>actual {s.actual}</span></> : null}
                    </span>
                    {s.stat && s.stat.n > 0 && s.stat.hit_rate != null && (
                      <span className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium"
                            title="Jak často predikovaný směr scénáře seděl se skutečným pohybem 1h po eventu (90 dní)"
                            style={{ background: s.stat.hit_rate >= 55 ? "#14532d55" : s.stat.hit_rate >= 45 ? "#78350f55" : "#7f1d1d55",
                                     color: s.stat.hit_rate >= 55 ? "#86efac" : s.stat.hit_rate >= 45 ? "#fcd34d" : "#fca5a5" }}>
                        ⌀ {s.stat.hit_rate}% ({s.stat.n})
                      </span>
                    )}
                  </div>
                  <div className="space-y-1">
                    {SCEN_ROWS.map(({ key, label }) => {
                      const leg = s[key];
                      const hit = s.realized === key;
                      return (
                        <div key={key}
                             className={`flex items-start gap-2 rounded-md px-2 py-1 text-[12px] ${hit ? "bg-[#1e2536] ring-1 ring-blue-500/40" : s.realized ? "opacity-40" : ""}`}>
                          <span className="w-28 shrink-0 text-gray-400">{label}</span>
                          <DirTag leg={leg} />
                          <span className="flex-1 text-gray-300">
                            {leg.text}
                            {hit && <span className="ml-1 rounded bg-blue-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">NASTALO</span>}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="mt-4 text-[10px] leading-relaxed text-gray-600">
            Skutečné hodnoty vydaných zpráv doplňujeme z investingLive pár minut po vydání (karta se sama obnovuje).{" "}
            <span className="text-gray-500">⌀ badge</span> = jak často predikovaný směr scénáře seděl se
            skutečným pohybem ceny ~1h po eventu (90 dní, počet v závorce). Edukativní mapování typických
            makro reakcí (pravidla + AI komentář), ne investiční doporučení — skutečný pohyb závisí na
            kontextu, pozicování a rétorice.
          </p>
        </>
      )}
    </div>
  );
}
