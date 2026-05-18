"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

const LOCAL_TZ = "Europe/Prague";

// High-impact categories that trigger a red dot
const HIGH_IMPACT_CATS = new Set([
  "monetary_policy", "central_bank_minutes", "inflation",
  "employment", "pmi", "gdp", "surprise_beat", "surprise_miss",
]);

interface Market {
  name: string;
  tz: string;
  openLocal: number;   // open hour in the market's OWN timezone
  closeLocal: number;  // close hour in the market's OWN timezone
  color: string;
}

// Using market-local times so DST is handled automatically:
//   London  8:00 BST/GMT  → always 9:00 Prague (CEST/CET)
//   New York 9:30 EDT/EST → always 15:30 Prague (CEST/CET)
//   Sydney  7:00 AEST     → ~23:00 Prague
//   Tokyo   9:00 JST      → ~2:00 Prague
const MARKETS: Market[] = [
  { name: "Sydney",   tz: "Australia/Sydney",  openLocal: 7,    closeLocal: 16,   color: "#fbbf24" },
  { name: "Tokyo",    tz: "Asia/Tokyo",         openLocal: 9,    closeLocal: 18,   color: "#c084fc" },
  { name: "London",   tz: "Europe/London",      openLocal: 8,    closeLocal: 16.5, color: "#60a5fa" },
  { name: "New York", tz: "America/New_York",   openLocal: 9.5,  closeLocal: 16,   color: "#34d399" },
];

const CLOCKS = [
  { name: "London",   tz: "Europe/London",    color: "#60a5fa" },
  { name: "New York", tz: "America/New_York", color: "#34d399" },
  { name: "Sydney",   tz: "Australia/Sydney", color: "#fbbf24" },
  { name: "Tokyo",    tz: "Asia/Tokyo",       color: "#c084fc" },
  { name: "Praha",    tz: LOCAL_TZ,           color: "#f97316" },
];

interface TimeParts { h: number; m: number; s: number; label: string }

interface CalendarEvent {
  id: number;
  title: string;
  published_at: string;
  categories: string[];
  max_weight: number;
}

function getTimeParts(tz: string, d: Date): TimeParts {
  const p = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(d);
  const g = (t: string) => parseInt(p.find(x => x.type === t)?.value ?? "0");
  const h = g("hour") % 24, m = g("minute"), s = g("second");
  return { h, m, s, label: `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}` };
}

function getUTCOffset(tz: string, d: Date): number {
  const local = getTimeParts(tz, d);
  const utcH = d.getUTCHours() + d.getUTCMinutes() / 60;
  const localH = local.h + local.m / 60;
  let offset = localH - utcH;
  if (offset < -12) offset += 24;
  if (offset > 12) offset -= 24;
  return offset;
}

// Convert a market-local hour to Prague-local decimal hours
function marketToDisplay(marketTz: string, marketHour: number, now: Date): number {
  const marketOffset = getUTCOffset(marketTz, now);
  const displayOffset = getUTCOffset(LOCAL_TZ, now);
  return (marketHour - marketOffset + displayOffset + 48) % 24;
}

// ─── Analog Clock SVG ────────────────────────────────────────────────
function Clock({ h, m, s, color, size = 60 }: { h: number; m: number; s: number; color: string; size?: number }) {
  const cx = size / 2, cy = size / 2, r = size / 2 - 2.5;

  const toXY = (deg: number, len: number) => {
    const rad = (deg - 90) * (Math.PI / 180);
    return { x: cx + Math.cos(rad) * len, y: cy + Math.sin(rad) * len };
  };

  const hDeg = ((h % 12) / 12) * 360 + (m / 60) * 30;
  const mDeg = (m / 60) * 360 + (s / 60) * 6;
  const sDeg = (s / 60) * 360;

  const hEnd = toXY(hDeg, r * 0.50);
  const mEnd = toXY(mDeg, r * 0.72);
  const sEnd = toXY(sDeg, r * 0.82);

  return (
    <svg width={size} height={size} className="drop-shadow-lg">
      <circle cx={cx} cy={cy} r={r} fill="rgba(10,12,22,0.92)" stroke={color} strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={4} opacity={0.08} />
      {Array.from({ length: 12 }, (_, i) => {
        const deg = (i / 12) * 360;
        const big = i % 3 === 0;
        const p1 = toXY(deg, r * (big ? 0.76 : 0.86));
        const p2 = toXY(deg, r * 0.94);
        return (
          <line key={i} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
            stroke={color} strokeWidth={big ? 1.5 : 0.8} opacity={big ? 0.8 : 0.4} />
        );
      })}
      <line x1={cx} y1={cy} x2={hEnd.x} y2={hEnd.y} stroke="white" strokeWidth={2.5} strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={mEnd.x} y2={mEnd.y} stroke="white" strokeWidth={1.5} strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={sEnd.x} y2={sEnd.y} stroke={color} strokeWidth={1} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={2.5} fill={color} />
    </svg>
  );
}

// ─── Session Bar ──────────────────────────────────────────────────────
function SessionBar({ market, now }: { market: Market; now: Date }) {
  const open  = marketToDisplay(market.tz, market.openLocal, now);
  const close = marketToDisplay(market.tz, market.closeLocal, now);
  const wraps = close < open;

  const pct = (h: number) => `${(h / 24) * 100}%`;
  const wid = (a: number, b: number) => `${((b - a) / 24) * 100}%`;

  const barStyle = (from: number, to: number): CSSProperties => ({
    position: "absolute",
    left: pct(from),
    width: wid(from, to),
    height: "100%",
    backgroundColor: market.color + "22",
    border: `1px solid ${market.color}44`,
    borderRadius: 4,
  });

  return (
    <div className="relative h-6">
      {!wraps ? (
        <div style={barStyle(open, close)} className="flex items-center overflow-hidden">
          <span className="px-2 text-[11px] font-medium truncate" style={{ color: market.color }}>
            {market.name}
          </span>
        </div>
      ) : (
        <>
          <div style={barStyle(0, close)} />
          <div style={{ ...barStyle(open, 24), borderRadius: 4 }} className="flex items-center overflow-hidden">
            <span className="px-2 text-[11px] font-medium truncate" style={{ color: market.color }}>
              {market.name}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────
export function MarketHoursBar() {
  const [now, setNow] = useState<Date | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    fetch("/api/news/events/today")
      .then(r => r.ok ? r.json() : [])
      .then(setEvents)
      .catch(() => {});
  }, []);

  if (!now) {
    return <div className="h-44 rounded-2xl bg-[#1a1d27] border border-[#2a2d3a] animate-pulse" />;
  }

  const local = getTimeParts(LOCAL_TZ, now);
  const localDecimal = local.h + local.m / 60 + local.s / 3600;
  const localOffset = getUTCOffset(LOCAL_TZ, now);
  const nowPct = `${(localDecimal / 24) * 100}%`;

  const isOpen = (m: Market) => {
    const open  = marketToDisplay(m.tz, m.openLocal, now);
    const close = marketToDisplay(m.tz, m.closeLocal, now);
    const wraps = close < open;
    return wraps
      ? localDecimal >= open || localDecimal <= close
      : localDecimal >= open && localDecimal <= close;
  };

  const axisHours = Array.from({ length: 13 }, (_, i) => i * 2);

  // Convert an event's published_at to Prague decimal hours
  const eventToDecimal = (iso: string): number => {
    const normalized = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
    const t = new Date(normalized);
    const parts = getTimeParts(LOCAL_TZ, t);
    return parts.h + parts.m / 60;
  };

  return (
    <div className="rounded-2xl border border-[#2a2d3a] bg-[#1a1d27] overflow-hidden">
      {/* ── Clocks row ── */}
      <div className="flex items-center justify-around gap-2 px-4 py-3 border-b border-[#2a2d3a]">
        {CLOCKS.map((c) => {
          const t = getTimeParts(c.tz, now);
          const market = c.name !== "Praha" ? MARKETS.find(m => m.name === c.name || m.tz === c.tz) : undefined;
          const marketOpen = market ? isOpen(market) : true;
          return (
            <div key={c.name} className="flex flex-col items-center gap-1">
              <div className="relative">
                <Clock h={t.h} m={t.m} s={t.s} color={c.color} size={60} />
                {c.name !== "Praha" && (
                  <div
                    className={`absolute bottom-0.5 right-0.5 w-2 h-2 rounded-full border border-[#1a1d27] ${
                      marketOpen ? "bg-green-500" : "bg-gray-600"
                    }`}
                  />
                )}
              </div>
              <div className="text-center leading-tight">
                <div className="text-[10px] text-gray-500">{c.name}</div>
                <div className="text-[13px] font-mono font-bold tabular-nums" style={{ color: c.color }}>
                  {t.label}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Timeline ── */}
      <div className="px-4 pb-3 pt-4">
        <div className="relative pt-5">
          {/* "Now" line + label */}
          <div
            className="absolute top-0 bottom-4 w-px z-10 pointer-events-none"
            style={{ left: nowPct, backgroundColor: "#f97316" }}
          >
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-full pb-0.5">
              <span className="text-[11px] font-mono font-bold text-orange-400 bg-[#1a1d27] border border-orange-800/60 rounded px-1 py-0.5 whitespace-nowrap">
                {local.label}
              </span>
            </div>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1 w-1.5 h-1.5 rounded-full bg-orange-500" />
          </div>

          {/* Grid lines — subtle vertical marks at every axis hour */}
          {axisHours.map((h) => (
            <div
              key={`grid-${h}`}
              className="absolute top-0 bottom-4 pointer-events-none"
              style={{
                left: `${(h / 24) * 100}%`,
                borderLeft: "1px solid rgba(255,255,255,0.05)",
              }}
            />
          ))}

          {/* Session bars */}
          <div className="space-y-1.5 mb-3 relative">
            {MARKETS.map((m) => (
              <SessionBar key={m.name} market={m} now={now} />
            ))}
          </div>

          {/* X-axis with hour labels */}
          <div className="relative h-4 border-t border-[#2a2d3a]/60">
            {axisHours.map((h) => (
              <span
                key={h}
                className="absolute -translate-x-1/2 top-0.5 text-[10px] text-gray-600 tabular-nums"
                style={{ left: `${(h / 24) * 100}%` }}
              >
                {String(h).padStart(2, "0")}
              </span>
            ))}
          </div>

          {/* Event dots row */}
          {events.length > 0 && (
            <div className="relative h-3 mt-0.5">
              {events.map((ev) => {
                const decimal = eventToDecimal(ev.published_at);
                const isHigh = ev.categories.some(c => HIGH_IMPACT_CATS.has(c));
                const color = isHigh ? "#ef4444" : "#f97316";
                return (
                  <div
                    key={ev.id}
                    className="absolute w-2 h-2 rounded-full -translate-x-1/2 top-0.5 cursor-help"
                    style={{ left: `${(decimal / 24) * 100}%`, backgroundColor: color }}
                    title={ev.title}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 pt-2 border-t border-[#2a2d3a]/40">
          {MARKETS.map((m) => {
            const open = isOpen(m);
            return (
              <div key={m.name} className="flex items-center gap-1.5 text-[10px]">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: m.color + "88", border: `1px solid ${m.color}` }} />
                <span className={open ? "text-gray-300" : "text-gray-600"}>{m.name}</span>
                <span className={`font-medium ${open ? "text-green-500" : "text-gray-600"}`}>
                  {open ? "OPEN" : "CLOSED"}
                </span>
              </div>
            );
          })}
          <div className="ml-auto text-[10px] text-gray-600">
            čas: Prague / CET{localOffset === 2 ? " (CEST +2)" : " (+1)"}
          </div>
          {events.length > 0 && (
            <div className="w-full flex items-center gap-3 text-[10px] text-gray-500 mt-0.5">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                <span>vysoký dopad</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-orange-500" />
                <span>střední dopad</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
