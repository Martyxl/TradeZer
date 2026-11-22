"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, Info, Loader2, Plus } from "lucide-react";
import { BROKERS, ANY_AFFILIATE } from "@/lib/affiliates";
import { AddTxModal } from "@/components/investments/TxModals";
import { fmtCzk, guessCurrency, saveProfile } from "./data";
import type { Action, ActionKind, AllocRow, ClassKey, Market, PlanKey, Profile } from "./types";

// Barvy tříd aktiv (sloupce rozložení, tečky).
export const CLASS_COLOR: Record<ClassKey, string> = {
  world: "#60b4ff", bonds: "#2dd4bf", gold: "#fbbf24", cash: "#9ca3af", stocks: "#a78bfa",
};

// Štítky akcí — třídy, které světlý motiv přemapuje na čitelné (globals.css).
export const KIND: Record<ActionKind, { label: string; cls: string }> = {
  buy: { label: "Koupit", cls: "bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-500/40" },
  trim: { label: "Zvážit prodej části", cls: "bg-red-950/50 text-red-300 ring-1 ring-inset ring-red-500/40" },
  wait: { label: "Počkej", cls: "bg-amber-950/50 text-amber-300 ring-1 ring-inset ring-amber-500/40" },
  rebalance: { label: "Nad plánem", cls: "bg-amber-950/50 text-amber-300" },
  tax: { label: "Daně", cls: "bg-blue-950/50 text-blue-300" },
  hold: { label: "Držet", cls: "bg-raised text-gray-300" },
};

export function KindPill({ kind, label }: { kind: ActionKind; label?: string }) {
  const k = KIND[kind];
  return <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${k.cls}`}>{label ?? k.label}</span>;
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-line bg-panel-2 p-4 md:p-5 ${className}`}>{children}</div>;
}

export function Stat({ label, value, sub, tone = "text-white" }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel-2 p-4">
      <div className="text-[11.5px] text-gray-500">{label}</div>
      <div className={`mt-0.5 text-xl font-bold ${tone}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

export function LoginNeeded({ what }: { what: string }) {
  return (
    <Card className="text-center">
      <p className="text-sm text-gray-300">{what}</p>
      <div className="mt-3 flex justify-center gap-2">
        <Link href="/registrace" className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-on-ink hover:bg-white/85">Vytvořit účet zdarma</Link>
        <Link href="/prihlaseni" className="rounded-full border border-line-2 px-4 py-2 text-sm text-gray-300 hover:text-white">Přihlásit</Link>
      </div>
    </Card>
  );
}

export function Disclaimer({ children }: { children?: React.ReactNode }) {
  return (
    <p className="flex items-start gap-1.5 text-[11.5px] leading-relaxed text-gray-500">
      <Info size={12} className="mt-0.5 shrink-0" />
      <span>{children ?? "Signály jsou pravidla tvého vlastního plánu a dat aplikace (valuace, daňový test, režim trhu). Nejde o investiční doporučení — rozhodnutí je vždy na tobě."}</span>
    </p>
  );
}

// ── Režim trhu + nálada ────────────────────────────────────────────────────
const REGIME_DOT: Record<string, string> = { calm: "#60ff82", recovering: "#60b4ff", tension: "#ffc440", panic: "#ff5050" };
const SENT_COLOR = (s: number) => (s < 25 ? "#ef4444" : s < 45 ? "#f97316" : s < 55 ? "#94a3b8" : s < 75 ? "#84cc16" : "#22c55e");

export function MarketCards({ market }: { market: Market }) {
  const { regime, sentiment } = market;
  if (!regime && !sentiment) return null;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {regime && (
        <Card>
          <div className="text-[11.5px] text-gray-500">Režim trhu</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="h-3 w-3 rounded-full" style={{ background: REGIME_DOT[regime.state] ?? "#9ca3af" }} />
            <span className="text-xl font-bold text-white">{regime.label}</span>
          </div>
          <p className="mt-1.5 text-sm text-gray-300">{regime.tip}</p>
        </Card>
      )}
      {sentiment && sentiment.score != null && (
        <Card>
          <div className="text-[11.5px] text-gray-500">Nálada investorů</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-bold text-white">{sentiment.score}</span>
            <span className="text-sm text-gray-400">/ 100 · {sentiment.label}</span>
          </div>
          <div className="relative mt-2 h-2 rounded-full bg-raised">
            <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${sentiment.score}%`, background: SENT_COLOR(sentiment.score) }} />
          </div>
          <div className="mt-1 flex justify-between text-[10.5px] text-gray-600"><span>strach</span><span>chamtivost</span></div>
          <p className="mt-1 text-sm text-gray-300">{sentiment.tip}</p>
        </Card>
      )}
    </div>
  );
}

// ── Seznam akcí „Co teď udělat" ─────────────────────────────────────────────
export function ActionList({ actions, onChanged, limit }: { actions: Action[]; onChanged?: () => void; limit?: number }) {
  const [adding, setAdding] = useState<Action | null>(null);
  const shown = limit ? actions.slice(0, limit) : actions;
  return (
    <>
      <ul className="divide-y divide-line">
        {shown.map((a, i) => (
          <li key={`${a.kind}-${a.symbol ?? a.cls ?? i}`} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:flex-wrap sm:items-start">
            <div className="w-auto sm:w-[132px] sm:pt-0.5"><KindPill kind={a.kind} /></div>
            <div className="min-w-0 flex-1 sm:min-w-[260px]">
              <div className="font-semibold text-white">{a.title}</div>
              {a.name && a.symbol && <div className="text-[11.5px] text-gray-500">{a.name}</div>}
              <p className="mt-0.5 text-[13.5px] leading-relaxed text-gray-300">{a.text}</p>
              {a.kind === "buy" && a.units != null && a.units > 0 && (
                <p className="mt-0.5 text-[12px] text-gray-500">≈ {a.units.toLocaleString("cs-CZ", { maximumFractionDigits: 2 })} ks za aktuální cenu</p>
              )}
            </div>
            {a.kind === "buy" && a.symbol && (
              <div className="flex shrink-0 flex-wrap items-center gap-1.5 sm:pl-[140px] xl:pl-0">
                <BrokerButtons size="sm" />
                {onChanged && (
                  <button onClick={() => setAdding(a)} className="flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[12px] text-gray-300 hover:text-white">
                    <Plus size={12} /> Zapsat nákup
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {adding && (
        <AddTxModal title={`Zapsat nákup ${adding.symbol}`} onClose={() => setAdding(null)}
          onSaved={() => { setAdding(null); onChanged?.(); }}
          initial={{
            tx_type: "buy", symbol: adding.symbol ?? "", name: adding.name ?? "",
            currency: adding.currency || guessCurrency(adding.symbol),
            ...(adding.price ? { price: String(adding.price) } : {}),
            ...(adding.units ? { quantity: String(adding.units >= 1 ? Math.floor(adding.units) : adding.units) } : {}),
          }} />
      )}
    </>
  );
}

// ── Rozložení portfolia vs. plán ───────────────────────────────────────────
export function AllocationBars({ rows }: { rows: AllocRow[] }) {
  if (!rows.length) return <p className="text-sm text-gray-500">Zatím nic nedržíš — první vklad se rozdělí podle plánu.</p>;
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const state = r.diff < -2 ? { t: "dokupovat", c: "text-emerald-300" } : r.diff > 2 ? { t: "nad cílem", c: "text-amber-300" } : { t: "v pořádku", c: "text-gray-400" };
        return (
          <div key={r.cls}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
              <span className="flex items-center gap-1.5 text-gray-200"><span className="h-2.5 w-2.5 rounded-full" style={{ background: CLASS_COLOR[r.cls] }} />{r.label}</span>
              <span className="text-gray-400">
                <b className="text-white">{r.pct.toLocaleString("cs-CZ")} %</b> / cíl {r.target} % · <span className={state.c}>{state.t}</span>
              </span>
            </div>
            <div className="relative mt-1 h-2.5 rounded-full bg-raised">
              <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.min(100, r.pct)}%`, background: CLASS_COLOR[r.cls] }} />
              {r.target > 0 && <div className="absolute -top-1 h-[18px] w-0.5 rounded bg-gray-200" style={{ left: `${r.target}%` }} title={`cíl ${r.target} %`} />}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Výběr plánu, měsíční vklad, rezerva ─────────────────────────────────────
const CLASS_KEYS: ClassKey[] = ["world", "bonds", "gold", "cash", "stocks"];

export function PlanEditor({ profile, onSaved }: { profile: Profile; onSaved: () => void }) {
  const [plan, setPlan] = useState<PlanKey>(profile.plan);
  const [monthly, setMonthly] = useState(String(profile.monthly_czk));
  const [reserve, setReserve] = useState(String(profile.reserve_czk));
  const [custom, setCustom] = useState<Record<ClassKey, string>>(() =>
    Object.fromEntries(CLASS_KEYS.map((c) => [c, String(profile.targets[c] ?? 0)])) as Record<ClassKey, string>);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const customSum = CLASS_KEYS.reduce((s, c) => s + (Number(custom[c]) || 0), 0);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const m = Number(monthly), r = Number(reserve);
      if (!Number.isFinite(m) || m < 0 || !Number.isFinite(r) || r < 0) throw new Error("Vklad i rezerva musí být kladná čísla.");
      if (plan === "custom" && Math.abs(customSum - 100) > 0.5) throw new Error(`Součet vlastního plánu musí být 100 % (teď ${customSum} %).`);
      await saveProfile({
        plan, monthly_czk: m, reserve_czk: r,
        ...(plan === "custom" ? { targets: Object.fromEntries(CLASS_KEYS.map((c) => [c, Number(custom[c]) || 0])) } : {}),
      });
      setMsg("Uloženo — plán je přepočítaný.");
      onSaved();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const options: [PlanKey, string, string][] = [
    ...(Object.entries(profile.plans) as [Exclude<PlanKey, "custom">, Profile["plans"]["careful"]][]).map(
      ([k, v]) => [k, v.label, v.for] as [PlanKey, string, string]),
    ["custom", "Vlastní", "Nastav si váhy sám."],
  ];
  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {options.map(([k, label, desc]) => {
          const t = k === "custom" ? null : profile.plans[k as Exclude<PlanKey, "custom">].targets;
          return (
            <button key={k} type="button" onClick={() => setPlan(k)} aria-pressed={plan === k}
              className={`rounded-xl border p-3 text-left transition-colors ${plan === k ? "border-[rgba(96,255,130,0.55)] bg-neon-tint" : "border-line bg-sunken hover:border-line-2"}`}>
              <div className="font-semibold text-white">{label}</div>
              <div className="mt-0.5 text-[12px] leading-snug text-gray-400">{desc}</div>
              {t && (
                <div className="mt-2 flex h-1.5 overflow-hidden rounded-full">
                  {CLASS_KEYS.filter((c) => t[c] > 0).map((c) => <span key={c} style={{ width: `${t[c]}%`, background: CLASS_COLOR[c] }} />)}
                </div>
              )}
            </button>
          );
        })}
      </div>
      {plan === "custom" && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {CLASS_KEYS.map((c) => (
            <label key={c} className="flex flex-col gap-1 text-[12px] text-gray-400">
              {profile.classes[c]}
              <input type="number" min={0} max={100} step={5} className="inv-input" value={custom[c]}
                onChange={(e) => setCustom((s) => ({ ...s, [c]: e.target.value }))} />
            </label>
          ))}
          <div className={`col-span-2 text-[12px] sm:col-span-5 ${Math.abs(customSum - 100) > 0.5 ? "text-amber-300" : "text-gray-500"}`}>Součet {customSum} % (musí být 100 %)</div>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-[12px] text-gray-400">
          Kolik měsíčně investuješ (Kč)
          <input type="number" min={0} step={500} className="inv-input" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-gray-400">
          Rezerva mimo brokera — spořicí účet, hotovost (Kč)
          <input type="number" min={0} step={1000} className="inv-input" value={reserve} onChange={(e) => setReserve(e.target.value)} />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={save} disabled={busy}
          className="flex items-center gap-1.5 rounded-full border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-4 py-2 text-sm font-semibold text-neon-soft hover:bg-[rgba(96,255,130,0.18)] disabled:opacity-50">
          {busy && <Loader2 size={14} className="animate-spin" />} Uložit plán
        </button>
        {msg && <span className="text-[12.5px] text-gray-400" role="status">{msg}</span>}
      </div>
    </div>
  );
}

// ── Brokeři (partnerské odkazy) ─────────────────────────────────────────────
export function BrokerButtons({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <>
      {BROKERS.map((b) => (
        <a key={b.key} href={b.url} target="_blank" rel={b.affiliate ? "sponsored noopener noreferrer" : "noopener noreferrer"}
          title={`${b.name}: ${b.pitch}${b.affiliate ? " (partnerský odkaz)" : ""}`}
          className={`inline-flex items-center gap-1 rounded-full border border-line-2 bg-raised font-semibold text-gray-200 hover:text-white ${
            size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3.5 py-1.5 text-[13px]"}`}>
          {b.name} <ExternalLink size={size === "sm" ? 10 : 12} />
        </a>
      ))}
    </>
  );
}

export function BrokerNote() {
  return (
    <div className="space-y-1 text-[11.5px] leading-relaxed text-gray-500">
      {ANY_AFFILIATE && <p>Odkazy na brokery jsou partnerské — když si přes ně založíš účet, Tradezer dostane odměnu a ty nic nepřiplatíš. Pomáhá to financovat provoz.</p>}
      {new Set(BROKERS.map((b) => b.risk)).size === 1
        ? <p>{BROKERS[0].risk}</p>
        : BROKERS.map((b) => <p key={b.key}><b className="text-gray-400">{b.name}:</b> {b.risk}</p>)}
    </div>
  );
}

export { fmtCzk };
