"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { dashFetch } from "@/lib/dashboardData";
import { calendarCovers, dayStatus, localDate, upcomingSpecialDays, type DayStatus, type MarketName } from "@/lib/marketCalendar";

const LOCAL_TZ = "Europe/Prague";

// High-impact categories that trigger a red dot
const HIGH_IMPACT_CATS = new Set([
  "monetary_policy", "central_bank_minutes", "inflation",
  "employment", "pmi", "gdp", "surprise_beat", "surprise_miss",
]);

interface Market {
  name: MarketName;
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

/** Pražská hodina (0–24, dnešní pražský den) → okamžik. */
function instantAt(now: Date, nowDecimal: number, h: number): Date {
  return new Date(now.getTime() + (h - nowDecimal) * 3_600_000);
}

/** Stav burzy v daném okamžiku podle jejího místního data (svátek / víkend / zkrácený den). */
function statusAt(m: Market, at: Date): DayStatus {
  return dayStatus(m.name, localDate(m.tz, at));
}

interface Segment { from: number; to: number; status: DayStatus; label: boolean }

/** Úseky session v dnešním pražském dni; každý úsek nese stav svého obchodního dne. */
function sessionSegments(m: Market, now: Date, nowDecimal: number): Segment[] {
  const open = marketToDisplay(m.tz, m.openLocal, now);
  const close = marketToDisplay(m.tz, m.closeLocal, now);
  const endOf = (start: number, st: DayStatus) => start + ((st.earlyClose ?? m.closeLocal) - m.openLocal);
  if (close >= open) {
    const st = statusAt(m, instantAt(now, nowDecimal, open + 0.01));
    return [{ from: open, to: Math.min(endOf(open, st), 24), status: st, label: true }];
  }
  // Session přes pražskou půlnoc (Sydney, Tokio): ranní kus patří obchodnímu dni, který začal včera.
  const stA = statusAt(m, instantAt(now, nowDecimal, close - 0.01));
  const stB = statusAt(m, instantAt(now, nowDecimal, open + 0.01));
  return [
    { from: 0, to: Math.max(0, endOf(open - 24, stA)), status: stA, label: false },
    { from: open, to: Math.min(endOf(open, stB), 24), status: stB, label: true },
  ];
}

const WD = ["ne", "po", "út", "st", "čt", "pá", "so"];
const dayLabel = (date: string) => {
  const d = new Date(`${date}T12:00:00Z`);
  return `${WD[d.getUTCDay()]} ${d.getUTCDate()}. ${d.getUTCMonth() + 1}.`;
};

/** Hodina zavření v místním čase burzy → pražský čas „HH:MM" pro daný den. */
const pragueTime = (m: Market, date: string, hour: number) => {
  const h = marketToDisplay(m.tz, hour, new Date(`${date}T12:00:00Z`));
  return `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`;
};

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
      <circle cx={cx} cy={cy} r={r} fill="var(--tz-clock)" stroke={color} strokeWidth={1.5} />
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
      <line x1={cx} y1={cy} x2={hEnd.x} y2={hEnd.y} stroke="rgb(var(--tz-ink))" strokeWidth={2.5} strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={mEnd.x} y2={mEnd.y} stroke="rgb(var(--tz-ink))" strokeWidth={1.5} strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={sEnd.x} y2={sEnd.y} stroke={color} strokeWidth={1} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={2.5} fill={color} />
    </svg>
  );
}

// ─── Session Bar ──────────────────────────────────────────────────────
function SessionBar({ market, now, nowDecimal, compact = false }: { market: Market; now: Date; nowDecimal: number; compact?: boolean }) {
  const pct = (h: number) => `${(h / 24) * 100}%`;
  const wid = (a: number, b: number) => `${((b - a) / 24) * 100}%`;

  const barStyle = (from: number, to: number, closed: boolean): CSSProperties => ({
    position: "absolute",
    left: pct(from),
    width: wid(from, to),
    height: "100%",
    borderRadius: 4,
    ...(closed
      ? { background: "repeating-linear-gradient(135deg, rgba(148,163,184,0.10) 0 4px, transparent 4px 8px)", border: "1px dashed rgba(148,163,184,0.35)" }
      : { backgroundColor: market.color + "22", border: `1px solid ${market.color}44` }),
  });

  return (
    <div className={`relative ${compact ? "h-4" : "h-6"}`}>
      {sessionSegments(market, now, nowDecimal).filter((s) => s.to > s.from).map((s) => {
        const closed = s.status.closed;
        const title = closed
          ? `${market.name}: zavřeno (${s.status.reason})`
          : s.status.earlyClose != null ? `${market.name}: zkrácený den (${s.status.earlyReason})` : market.name;
        const suffix = closed
          ? ` · zavřeno${s.status.reason !== "víkend" ? ` (${s.status.reason})` : ""}`
          : s.status.earlyClose != null ? " · zkráceně" : "";
        return (
          <div key={s.from} style={barStyle(s.from, s.to, closed)} className="flex items-center overflow-hidden" title={title}>
            {s.label && (
              <span className={`truncate font-medium ${compact ? "px-1 text-[9px]" : "px-2 text-[11px]"}`}
                style={{ color: closed ? "rgb(148,163,184)" : market.color }}>
                {market.name}{suffix}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────
/** compact = úzká verze do pravého sloupce dashboardu (menší hodiny, nižší pruhy). */
export function MarketHoursBar({ compact = false }: { compact?: boolean }) {
  const [now, setNow] = useState<Date | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    dashFetch("/api/news/events/today")
      .then(r => r.ok ? r.json() : [])
      .then(setEvents)
      .catch(() => {});
  }, []);

  if (!now) {
    return <div className={`${compact ? "h-32" : "h-44"} rounded-2xl bg-panel border border-line animate-pulse`} />;
  }

  const local = getTimeParts(LOCAL_TZ, now);
  const localDecimal = local.h + local.m / 60 + local.s / 3600;
  const localOffset = getUTCOffset(LOCAL_TZ, now);
  const nowPct = `${(localDecimal / 24) * 100}%`;

  // Otevřeno = obchodní den burzy (ne víkend / svátek) a místní čas burzy v rámci session (i zkrácené).
  const isOpen = (m: Market) => {
    const st = statusAt(m, now);
    if (st.closed) return false;
    const t = getTimeParts(m.tz, now);
    const dec = t.h + t.m / 60;
    return dec >= m.openLocal && dec < (st.earlyClose ?? m.closeLocal);
  };
  const todayPrague = localDate(LOCAL_TZ, now);
  const special = upcomingSpecialDays(todayPrague, 14);

  const axisHours = compact ? Array.from({ length: 7 }, (_, i) => i * 4) : Array.from({ length: 13 }, (_, i) => i * 2);

  // Convert an event's published_at to Prague decimal hours
  const eventToDecimal = (iso: string): number => {
    const normalized = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
    const t = new Date(normalized);
    const parts = getTimeParts(LOCAL_TZ, t);
    return parts.h + parts.m / 60;
  };

  return (
    <div className="rounded-2xl border border-line bg-panel overflow-hidden">
      {/* ── Clocks row ── */}
      <div className={`flex items-center justify-around border-b border-line ${compact ? "gap-1 px-2 py-2" : "gap-2 px-4 py-3"}`}>
        {CLOCKS.map((c) => {
          const t = getTimeParts(c.tz, now);
          const market = c.name !== "Praha" ? MARKETS.find(m => m.name === c.name || m.tz === c.tz) : undefined;
          const marketOpen = market ? isOpen(market) : true;
          return (
            <div key={c.name} className="flex flex-col items-center gap-1">
              <div className="relative">
                <Clock h={t.h} m={t.m} s={t.s} color={c.color} size={compact ? 34 : 60} />
                {c.name !== "Praha" && (
                  <div
                    className={`absolute bottom-0.5 right-0.5 w-2 h-2 rounded-full border border-[color:var(--tz-panel-2)] ${
                      marketOpen ? "bg-green-500" : "bg-gray-600"
                    }`}
                  />
                )}
              </div>
              <div className="text-center leading-tight">
                <div className={`${compact ? "text-[9px]" : "text-[10px]"} text-gray-500`}>{c.name}</div>
                <div className={`${compact ? "text-[11px]" : "text-[13px]"} font-mono font-bold tabular-nums`} style={{ color: c.color }}>
                  {t.label}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Timeline ── */}
      <div className={compact ? "px-3 pb-2 pt-3" : "px-4 pb-3 pt-4"}>
        <div className="relative pt-5">
          {/* "Now" line + label */}
          <div
            className="absolute top-0 bottom-4 w-px z-10 pointer-events-none"
            style={{ left: nowPct, backgroundColor: "#f97316" }}
          >
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-full pb-0.5">
              <span className={`${compact ? "text-[9px]" : "text-[11px]"} font-mono font-bold text-orange-400 bg-panel border border-orange-800/60 rounded px-1 py-0.5 whitespace-nowrap`}>
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

          {/* Session bars (svátek / víkend = šrafovaně, zkrácený den = kratší pruh) */}
          <div className={`relative ${compact ? "mb-2 space-y-1" : "mb-3 space-y-1.5"}`}>
            {MARKETS.map((m) => (
              <SessionBar key={m.name} market={m} now={now} nowDecimal={localDecimal} compact={compact} />
            ))}
          </div>

          {/* X-axis with hour labels */}
          <div className="relative h-4 border-t border-line/60">
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
        <div className={`flex flex-wrap border-t border-line/40 ${compact ? "mt-1.5 gap-x-3 gap-y-0.5 pt-1.5" : "mt-2 gap-x-4 gap-y-1 pt-2"}`}>
          {MARKETS.map((m) => {
            const open = isOpen(m);
            const st = statusAt(m, now);
            const holiday = st.closed && st.reason !== "víkend" ? st.reason : null;
            return (
              <div key={m.name} className="flex items-center gap-1.5 text-[10px]">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: m.color + "88", border: `1px solid ${m.color}` }} />
                <span className={open ? "text-gray-300" : "text-gray-600"}>{m.name}</span>
                <span className={`font-medium ${open ? "text-green-500" : holiday ? "text-amber-500" : "text-gray-600"}`}>
                  {open ? "OPEN" : "CLOSED"}
                  {holiday && ` · ${holiday}`}
                  {!st.closed && st.earlyClose != null && ` · do ${pragueTime(m, localDate(m.tz, now), st.earlyClose)}`}
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

        {/* Kalendář: svátky a zkrácené dny burz na 14 dní dopředu (časy v Praze) */}
        <div className={`border-t border-line/40 ${compact ? "mt-1.5 pt-1.5" : "mt-2 pt-2"}`}>
          <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Svátky burz · 14 dní</div>
          {special.length === 0 ? (
            <div className="text-[10.5px] text-gray-600">
              {calendarCovers(todayPrague) ? "Žádné svátky ani zkrácené dny — jen víkendy." : "Kalendář svátků je potřeba doplnit na další rok."}
            </div>
          ) : (
            <ul className="space-y-0.5">
              {special.slice(0, compact ? 5 : 8).map((d) => {
                const m = MARKETS.find((x) => x.name === d.market)!;
                const today = d.date === localDate(m.tz, now);
                return (
                  <li key={d.market + d.date} className="flex items-baseline gap-1.5 text-[10.5px]">
                    <span className={`w-12 shrink-0 tabular-nums ${today ? "font-semibold text-amber-400" : "text-gray-500"}`}>
                      {today ? "dnes" : dayLabel(d.date)}
                    </span>
                    <span className="h-1.5 w-1.5 shrink-0 self-center rounded-full" style={{ backgroundColor: m.color }} />
                    <span className="shrink-0 text-gray-300">{d.market}</span>
                    <span className={`shrink-0 ${d.closed ? "text-amber-500" : "text-gray-400"}`}>
                      {d.closed ? "zavřeno" : `zkráceně do ${pragueTime(m, d.date, d.earlyClose!)}`}
                    </span>
                    <span className="truncate text-gray-600">{d.label}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
