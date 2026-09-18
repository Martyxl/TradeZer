"use client";

import { useEffect, useState } from "react";
import { Activity, Info } from "lucide-react";

interface ProfilePoint { strike: number; gex: number }
interface Instrument {
  underlying: string; spot: number; net_gex: number;
  regime: "positive" | "negative"; flip: number | null;
  call_wall: number | null; put_wall: number | null;
  profile: ProfilePoint[]; contracts: number;
}
interface Resp {
  generated: string | null; ticker: string;
  instrument: Instrument | null; note?: string;
}

function fmtGex(v: number): string {
  const a = Math.abs(v);
  const s = v >= 0 ? "+" : "−";
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)} mld`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(0)} mil`;
  return `${s}$${a.toFixed(0)}`;
}

export function GammaCard({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Instrument | null>(null);
  const [gen, setGen] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty">("loading");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    setState("loading");
    fetch(`/api/gamma?ticker=${ticker}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j: Resp) => {
        if (!alive) return;
        if (j.instrument) { setD(j.instrument); setGen(j.generated); setState("ready"); }
        else { setD(null); setState("empty"); }
      })
      .catch(() => { if (alive) setState("empty"); });
    return () => { alive = false; };
  }, [ticker]);

  // Instrument bez options proxy (nebo bez dat) — kartu nezobrazuj vůbec.
  if (state === "empty") return null;

  const positive = d?.regime === "positive";
  const accent = positive ? "#4ade80" : "#f87171";
  // Top strikes dle |gex| (walls), seřazené shora dolů (vysoký strike nahoře).
  const bars = d
    ? [...d.profile].sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex)).slice(0, 12)
        .sort((a, b) => b.strike - a.strike)
    : [];
  const maxAbs = bars.reduce((m, p) => Math.max(m, Math.abs(p.gex)), 1);

  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#1a1d27] p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-indigo-400" />
          <h3 className="text-sm font-semibold text-white">Gamma (GEX)</h3>
          {d && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#232735] text-gray-400 font-mono">
              {d.underlying}
            </span>
          )}
          <button onClick={() => setOpen(!open)} className="text-gray-500 hover:text-gray-300">
            <Info size={13} />
          </button>
        </div>
        {gen && (
          <span className="text-[10px] text-gray-500">
            {new Date(gen).toLocaleString("cs", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      {open && (
        <div className="mb-3 rounded-lg border border-[#2a2d3a] bg-[#151823] p-3 text-[11px] text-gray-400 leading-relaxed">
          <b className="text-gray-300">Model z options open interest, ne signál.</b> Pozitivní gamma
          = dealeři tlumí pohyby (mean-revert, klidnější trh). Negativní gamma = dealeři pohyby
          zesilují (trendové, volatilní). <b>Flip</b> = úroveň, kde se režim mění. <b>Call wall</b> =
          strike s max call gamma (rezistence/magnet), <b>Put wall</b> = max put gamma (support).
          OI je snapshot z předešlé noci — statické přes den.
        </div>
      )}

      {state === "loading" && (
        <div className="h-40 rounded-lg bg-[#151823] animate-pulse" />
      )}

      {d && (
        <>
          <div className="flex items-center gap-3 mb-4">
            <span
              className="text-xs font-semibold px-2 py-1 rounded"
              style={{ color: accent, backgroundColor: positive ? "rgba(74,222,128,0.12)" : "rgba(248,113,113,0.12)" }}
            >
              {positive ? "Pozitivní gamma" : "Negativní gamma"}
            </span>
            <span className="font-mono text-lg font-bold" style={{ color: accent }}>{fmtGex(d.net_gex)}</span>
            <span className="text-[11px] text-gray-500">/ 1% pohyb · {d.contracts} kontraktů</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4 text-center">
            {[
              { l: "Spot", v: d.spot, c: "#e5e7eb" },
              { l: "Flip", v: d.flip, c: "#a78bfa" },
              { l: "Call wall", v: d.call_wall, c: "#4ade80" },
              { l: "Put wall", v: d.put_wall, c: "#f87171" },
            ].map((x) => (
              <div key={x.l} className="rounded-lg bg-[#151823] border border-[#232735] py-2">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">{x.l}</div>
                <div className="font-mono text-sm font-semibold" style={{ color: x.c }}>
                  {x.v != null ? x.v : "—"}
                </div>
              </div>
            ))}
          </div>

          {bars.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5">
                GEX profil (net po strikech, kolem spotu)
              </div>
              <div className="space-y-1">
                {bars.map((p) => {
                  const w = (Math.abs(p.gex) / maxAbs) * 50; // % šířky z poloviny
                  const pos = p.gex >= 0;
                  const nearSpot = d.spot && Math.abs(p.strike - d.spot) / d.spot < 0.006;
                  return (
                    <div key={p.strike} className="flex items-center gap-2 text-[10px]">
                      <span className={`w-12 text-right font-mono ${nearSpot ? "text-white font-bold" : "text-gray-500"}`}>
                        {p.strike}
                      </span>
                      <div className="relative flex-1 h-3 flex items-center">
                        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[#3a3f52]" />
                        <div
                          className="absolute h-2 rounded-sm"
                          style={{
                            [pos ? "left" : "right"]: "50%",
                            width: `${w}%`,
                            backgroundColor: pos ? "rgba(74,222,128,0.75)" : "rgba(248,113,113,0.75)",
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
