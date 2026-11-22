"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus, Upload, Settings2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { AddTxModal, ImportModal } from "@/components/investments/TxModals";
import { usePlan, fmtCzk, fmtPct, dateCs, companyHref } from "@/components/investor/data";
import { AllocationBars, Card, CLASS_COLOR, Disclaimer, KindPill, LoginNeeded, PlanEditor, Stat } from "@/components/investor/ui";
import type { SimplePosition } from "@/components/investor/types";

const TAG_LABEL: Record<SimplePosition["tag"], string> = { buy: "Dokoupit", trim: "Ubrat", wait: "Počkej", hold: "Držet" };

// Režim Začátečník — Moje portfolio: plán (cílové rozložení + vklad), rozložení vs. cíl, pozice s daní.
export default function InvestorPortfolio() {
  const { user, loading: authLoading } = useAuth();
  const { data, error, reload } = usePlan();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);

  if (authLoading) return <div className="h-40 animate-pulse rounded-2xl bg-panel" />;
  if (!user) return <LoginNeeded what="Ulož si svoje portfolio a plán — uvidíš, co dokoupit, co je nad plánem a kdy můžeš prodat bez daně." />;

  // Hlavička s tlačítky je vždy vidět — i když se plán nenačte, jde zapsat nákup nebo importovat výpis.
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-white">Moje portfolio</h1>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setImporting(true)} className="flex items-center gap-1.5 rounded-full border border-line px-3.5 py-2 text-sm text-gray-200 hover:text-white">
            <Upload size={14} /> Import z XTB
          </button>
          <button onClick={() => setAdding(true)} className="flex items-center gap-1.5 rounded-full border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-3.5 py-2 text-sm font-semibold text-neon-soft hover:bg-[rgba(96,255,130,0.18)]">
            <Plus size={14} /> Zapsat nákup
          </button>
        </div>
      </div>
  );
  const modals = (
    <>
      {adding && <AddTxModal title="Zapsat nákup" onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload(); }} initial={{ tx_type: "buy", currency: "EUR" }} />}
      {importing && <ImportModal onClose={() => setImporting(false)} onDone={() => { setImporting(false); reload(); }} />}
    </>
  );
  if (error || !data) {
    return (
      <div className="space-y-5">
        {header}
        {error
          ? <Card><p className="text-sm text-amber-300">Portfolio se nepodařilo načíst. Zkus to za chvíli znovu (nákup můžeš zapsat i tak).</p></Card>
          : <div className="space-y-4"><div className="h-24 animate-pulse rounded-2xl bg-panel" /><div className="h-72 animate-pulse rounded-2xl bg-panel" /></div>}
        {modals}
      </div>
    );
  }

  const t = data.totals;
  const p = data.profile;
  const planLabel = p.plan === "custom" ? "Vlastní" : p.plans[p.plan as "careful"]?.label;
  const showEditor = editing || !p.plan_set;
  const now = data.invest_now;
  const upPct = t.invested ? (t.unrealized / t.invested) * 100 : null;

  return (
    <div className="space-y-5">
      {header}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Hodnota" value={fmtCzk(t.value)} sub={!t.complete ? "u některých pozic chybí cena" : undefined} />
        <Stat label="Zisk / ztráta" value={fmtCzk(t.unrealized)} sub={fmtPct(upPct)}
          tone={t.unrealized > 0 ? "text-neon" : t.unrealized < 0 ? "text-[#ff5050]" : "text-white"} />
        <Stat label="Bez daně už teď" value={fmtCzk(t.tax_free)} sub="drženo přes 3 roky" />
        <Stat label="Ještě v daňovém testu" value={fmtCzk(t.tax_pending)} sub="při prodeji by se zisk danil" />
      </div>

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-[15px] font-bold text-white">Můj investiční typ: {planLabel}</h2>
            <p className="text-[12.5px] text-gray-500">
              Měsíčně {fmtCzk(p.monthly_czk)}
              {now.capital > 0 ? ` · volné peníze ${fmtCzk(now.capital)}` : ""}
              {p.reserve_czk ? ` · rezerva ${fmtCzk(p.reserve_czk)}` : ""}
            </p>
          </div>
          {p.plan_set && (
            <button onClick={() => setEditing((e) => !e)} className="flex items-center gap-1.5 rounded-full border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.08)] px-3 py-1.5 text-[12.5px] font-semibold text-neon-soft hover:bg-[rgba(96,255,130,0.14)]">
              <Settings2 size={13} /> {editing ? "Zavřít" : "Změnit typ a částky"}
            </button>
          )}
        </div>
        {showEditor && (
          <div className="mb-5 border-b border-line pb-5">
            {!p.plan_set && (
              <p className="mb-3 text-[13px] text-gray-300">
                Zatím máš jen výchozí typ <b className="text-white">{planLabel}</b>. Vyber ten, který odpovídá tobě, a zadej,
                kolik můžeš investovat — podle toho se spočítá, co přesně koupit.
              </p>
            )}
            <PlanEditor key={`${p.plan}-${p.monthly_czk}-${p.reserve_czk}-${p.capital_left}`} profile={p} onSaved={() => { setEditing(false); reload(); }} />
          </div>
        )}
        <AllocationBars rows={data.allocation.classes} />
        {data.contribution.length > 0 && (
          <div className="mt-4 rounded-xl border border-line bg-sunken p-3">
            <div className="text-[12.5px] font-semibold text-white">
              Teď rozděl {fmtCzk(now.total)} takto
              {now.capital > 0 && <span className="font-normal text-gray-500"> (měsíční vklad {fmtCzk(now.monthly)} + volné peníze {fmtCzk(now.capital)})</span>}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-gray-300">
              {data.contribution.map((c) => (
                <span key={c.cls} className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLOR[c.cls] }} />{c.label}: <b className="text-white">{fmtCzk(c.amount)}</b>
                </span>
              ))}
            </div>
            <p className="mt-1.5 text-[11.5px] text-gray-500">Vklad jde hlavně do částí pod cílem — portfolio se tak srovnává samo, bez prodávání. Konkrétní nákupy jsou v <Link href="/investor" className="underline hover:text-gray-300">Přehledu</Link>.</p>
          </div>
        )}
        {data.allocation.unpriced.length > 0 && (
          <p className="mt-2 text-[11.5px] text-gray-500">Bez aktuální ceny (zatím se nepočítají): {data.allocation.unpriced.join(", ")}. Ceny se doplňují během dne.</p>
        )}
      </Card>

      <Card className="p-0 md:p-0">
        <div className="border-b border-line px-4 py-3 md:px-5">
          <h2 className="text-[15px] font-bold text-white">Pozice</h2>
        </div>
        {data.positions.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-500 md:px-5">Zatím žádné pozice. Zapiš první nákup, nebo nahraj výpis z XTB.</p>
        ) : (
          <ul className="divide-y divide-line">
            {data.positions.map((x) => (
              <li key={x.symbol} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 md:px-5">
                <div className="w-[118px] shrink-0">
                  <KindPill kind={x.tag} label={x.tag === "wait" && x.tax_free_from ? `Počkej do ${dateCs(x.tax_free_from).replace(/\s?\d{4}$/, "")}` : TAG_LABEL[x.tag]} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    {x.cls === "stocks"
                      ? <Link href={companyHref(x.symbol)} className="font-semibold text-white hover:underline" title="Proč — zjednodušená karta firmy">{x.symbol.split(".")[0]}</Link>
                      : <span className="font-semibold text-white">{x.symbol.split(".")[0]}</span>}
                    <span className="truncate text-[12px] text-gray-500">{x.name}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-2 text-[12px] text-gray-500">
                    <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLOR[x.cls] }} />{x.class_label}</span>
                    <span>· {x.tax_free_all ? "celé bez daně" : x.tax_free_part ? `část bez daně, zbytek od ${dateCs(x.tax_free_from)}` : x.tax_free_from ? `bez daně od ${dateCs(x.tax_free_from)}` : ""}</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[13.5px] text-white">{fmtCzk(x.value)}</div>
                  <div className="text-[12px] text-gray-500">
                    {x.weight != null ? `${x.weight.toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} % · ` : ""}
                    <span className={x.unrealized_pct == null ? "" : x.unrealized_pct >= 0 ? "text-neon" : "text-[#ff5050]"}>{fmtPct(x.unrealized_pct)}</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="border-t border-line px-4 py-3 text-[11.5px] text-gray-500 md:px-5">
          Všechny transakce, prodeje po jednotlivých nákupech, dividendy a podrobný daňový test najdeš v{" "}
          <Link href="/investice" className="underline hover:text-gray-300">investičním deníku</Link> a na stránce{" "}
          <Link href="/dane" className="underline hover:text-gray-300">Daně</Link> — data jsou stejná.
        </p>
      </Card>

      <Disclaimer>Daňový test: v ČR je zisk z prodeje cenných papírů držených déle než 3 roky osvobozen od daně (počítáno po jednotlivých nákupech, nejstarší se prodávají první). Orientační výpočet, nejde o daňové poradenství.</Disclaimer>

      {modals}
    </div>
  );
}
