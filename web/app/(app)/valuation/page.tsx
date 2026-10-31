"use client";

import { useEffect, useState } from "react";
import { Target, LayoutGrid, Table2, Info, Loader2 } from "lucide-react";
import { BubbleMap, VERDICT_COLOR, ZONE_COLOR, ZONE_LABEL, zoneText, type OverviewItem, type ZoneCurves } from "@/components/valuation/BubbleMap";
import { ValuationDetail } from "@/components/valuation/ValuationDetail";
import { EarningsFeed, alertTitle, earningsAlerts, useReports, type EarningsReport } from "@/components/valuation/EarningsReports";
import { PaywallGuard } from "@/components/PaywallGuard";
import { authHeaders } from "@/lib/auth";

interface Group { key: string; label_cs: string; color_hex: string }

// Placená záložka (Trader+): server-side gate + UX upsell. Inner se mountuje jen když entitled.
export default function ValuationPage() {
  return (
    <PaywallGuard tier="trader" name="Valuation Radar">
      <ValuationInner />
    </PaywallGuard>
  );
}

function ValuationInner() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [items, setItems] = useState<OverviewItem[]>([]);
  const [zones, setZones] = useState<ZoneCurves | null>(null);
  const [group, setGroup] = useState<string | null>(null);
  const [view, setView] = useState<"map" | "table">("map");
  const [selected, setSelected] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [portfolio, setPortfolio] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [addQuery, setAddQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [addMsg, setAddMsg] = useState<string | null>(null);
  const reports = useReports("/api/valuation/earnings?limit=30");
  const alerts = earningsAlerts(reports);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("ticker");
    if (t && /^[A-Za-z0-9.-]{1,12}$/.test(t)) setSelected(t.toUpperCase());
  }, []);

  useEffect(() => {
    fetch("/api/valuation/groups", { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null)).then((d) => setGroups(d?.groups ?? [])).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const p = new URLSearchParams();
    if (group) p.set("group", group);
    if (portfolio) p.set("portfolio", "true");
    const qs = p.toString();
    fetch(`/api/valuation/overview${qs ? "?" + qs : ""}`, { cache: "no-store", headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setItems(d?.items ?? []); setZones(d?.zones ?? null); setAsOf(d?.meta?.as_of_date ?? null); })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [group, portfolio, refreshKey]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const q = addQuery.trim();
    if (!q) return;
    setAdding(true); setAddMsg(null);
    try {
      const res = await fetch("/api/valuation/request", {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ query: q }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setAddMsg(d.message || `${d.ticker} (${d.name}) přidáno.`);
        setAddQuery("");
        setRefreshKey((k) => k + 1);
        // Firma už je spočítaná (nová nebo dříve přidaná jiným uživatelem) → rovnou otevři její detail
        if (d.computed && d.ticker) setSelected(d.ticker);
      } else {
        setAddMsg(d.detail || "Nepodařilo se přidat.");
      }
    } catch {
      setAddMsg("Chyba připojení.");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Target size={18} className="text-blue-400" />
            <h1 className="text-2xl font-bold text-white">Valuation Radar</h1>
          </div>
          <span className="text-xs text-gray-500">
            fundamentální filtr pro delší horizont{asOf ? ` · k ${asOf}` : ""}
          </span>
          <div className="ml-auto flex items-center gap-1 rounded-lg border border-[#2a2d3a] p-0.5">
            <button onClick={() => setView("map")}
              className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs ${view === "map" ? "bg-[#1e2536] text-white" : "text-gray-400"}`}>
              <LayoutGrid size={13} /> Mapa
            </button>
            <button onClick={() => setView("table")}
              className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs ${view === "table" ? "bg-[#1e2536] text-white" : "text-gray-400"}`}>
              <Table2 size={13} /> Tabulka
            </button>
          </div>
        </div>
        <p className="text-sm text-gray-400 mt-1">
          Deterministické skóre valuace z veřejných fundamentů. Není obchodní signál ani investiční doporučení.
        </p>
      </div>

      {/* filtr skupin */}
      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => setGroup(null)}
          className={`rounded-full px-3 py-1 text-xs border ${!group ? "bg-[#1e2536] text-white border-[#2f3b55]" : "bg-[#151823] text-gray-400 border-[#2a2d3a]"}`}>
          Vše
        </button>
        {groups.map((g) => (
          <button key={g.key} onClick={() => setGroup(g.key)}
            className={`rounded-full px-3 py-1 text-xs border ${group === g.key ? "text-white" : "text-gray-400"}`}
            style={{ borderColor: group === g.key ? g.color_hex : "#2a2d3a",
                     background: group === g.key ? g.color_hex + "22" : "#151823" }}>
            {g.label_cs}
          </button>
        ))}
        <button onClick={() => setPortfolio((v) => !v)}
          className={`ml-auto rounded-full px-3 py-1 text-xs border ${portfolio
            ? "bg-[rgba(96,255,130,0.14)] text-[#8fffab] border-[rgba(96,255,130,0.4)]"
            : "bg-[#151823] text-gray-400 border-[#2a2d3a] hover:text-white"}`}>
          {portfolio ? "✓ " : ""}Jen moje portfolio
        </button>
      </div>

      {/* Přidat akcii na přání */}
      <form onSubmit={handleAdd} className="flex flex-wrap items-center gap-2">
        <input value={addQuery} onChange={(e) => setAddQuery(e.target.value)}
          placeholder="Přidat akcii k výpočtu — ticker nebo název (např. AAPL / Palantir)"
          className="min-w-[280px] flex-1 rounded-lg border border-[#2a2d3a] bg-[#0f1117] px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-[#60ff82]" />
        <button type="submit" disabled={adding || !addQuery.trim()}
          className="flex items-center gap-1.5 rounded-lg border border-[rgba(96,255,130,0.4)] bg-[rgba(96,255,130,0.12)] px-4 py-2 text-sm font-medium text-[#8fffab] hover:bg-[rgba(96,255,130,0.18)] disabled:opacity-50">
          {adding && <Loader2 size={14} className="animate-spin" />} Přidat
        </button>
        {addMsg && <span className="text-xs text-gray-400">{addMsg}</span>}
      </form>

      {loading ? (
        <div className="flex h-[460px] flex-col items-center justify-center gap-3 rounded-xl border border-[#2a2d3a] bg-[#151823] text-gray-400">
          <Loader2 size={30} className="animate-spin text-blue-400" />
          <div className="text-sm font-medium text-gray-300">Načítám data valuace…</div>
          <div className="max-w-xs text-center text-[11px] text-gray-600">
            Po delší nečinnosti může první načtení trvat ~10&nbsp;s (server se probouzí). Vydrž, není potřeba obnovovat stránku.
          </div>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-6 text-center text-sm text-yellow-300">
          <Info size={18} className="inline mb-1" /><br />
          {portfolio
            ? "Žádný z tvých titulů zatím není ve výpočtu. Přidej ho výše polem nahoře (ticker nebo název firmy)."
            : "Zatím nejsou k dispozici žádná skóre. Přidej akcii výše, nebo spusť přepočet (POST /api/valuation/refresh)."}
        </div>
      ) : view === "map" ? (
        <>
          <BubbleMap items={items} onSelect={setSelected} zones={zones} alerts={alerts} />
          <Legend />
          {zones && <ZoneNote />}
        </>
      ) : (
        <ValuationTable items={items} onSelect={setSelected} alerts={alerts} />
      )}

      {/* Výsledky hospodaření firem (SEC 8-K → vysvětlení ze Sparku) */}
      <EarningsFeed reports={reports} onTicker={setSelected} />

      <p className="text-[11px] text-gray-500">
        Skóre je heuristika nad veřejnými daty s nejistou kvalitou, ne ocenění firmy. Konsenzus analytiků bývá
        systematicky optimistický. Slouží jako rozcestník k dalšímu zkoumání, ne jako rozhodovací mechanismus.
      </p>

      {selected && <ValuationDetail ticker={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-[11px] text-gray-500">
      {Object.entries(VERDICT_COLOR).map(([v, c]) => (
        <span key={v} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} /> {v}
        </span>
      ))}
      <span className="flex items-center gap-1.5"><span className="text-red-400">⚠</span> bublina (drahé + zpomaluje + revize dolů)</span>
      <span className="flex items-center gap-1.5"><AlertMark /> nové výsledky hospodaření — prověř (viz sekce dole)</span>
      <span>velikost = tržní kapitalizace</span>
    </div>
  );
}

function ZoneNote() {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] p-3 text-[11px] leading-relaxed text-gray-400">
      <div className="mb-1 flex flex-wrap gap-4">
        {(["buy", "hold", "avoid"] as const).map((z) => (
          <span key={z} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: ZONE_COLOR[z], opacity: z === "hold" ? 0.5 : 0.8 }} />
            {ZONE_LABEL[z]}
          </span>
        ))}
      </div>
      <p>
        <b className="text-gray-300">Jak zóny vznikají:</b> čím dražší je firma vůči své vlastní historii (vpravo), tím vyšší
        očekávaný růst zisku (nahoře) musí cenu ospravedlnit. Nad zelenou čárou je firma levná vzhledem k růstu, pod
        červenou drahá vzhledem k růstu; mezi nimi je pásmo „držet / sledovat“.
      </p>
      <p className="mt-1 text-yellow-500/80">
        Orientační pravidlo, ne doporučení. Hranice vychází z logiky skórování, zatím NENÍ ověřená historickou
        výnosností (skóre sbíráme teprve od srpna 2026). Odhady analytiků bývají optimistické a data mohou být
        neúplná — vždy si informace ověř (výsledky firmy, zadlužení, důvod levnosti) a rozhodni se sám.
      </p>
      <p className="mt-1">
        <b className="text-gray-300">(?) = nespolehlivá zóna:</b> extrémní růst zisku nad 100 % (často srovnání s loňským
        ziskem sníženým jednorázovými položkami, ne skutečný růst) nebo nízká důvěra v data. U takové firmy zónu neber vážně.
      </p>
    </div>
  );
}

function AlertMark({ title }: { title?: string }) {
  return (
    <span title={title} className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-yellow-400 text-[10px] font-black leading-none text-[#0b0e16]">!</span>
  );
}

function ValuationTable({ items, onSelect, alerts }: {
  items: OverviewItem[]; onSelect: (t: string) => void; alerts: Record<string, EarningsReport>;
}) {
  return (
    <div className="rounded-xl border border-[#2a2d3a] bg-[#151823] overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 text-[10px] uppercase border-b border-[#2a2d3a]">
            <th className="text-left px-3 py-2">Ticker</th>
            <th className="text-right px-3 py-2">Valuace</th>
            <th className="text-right px-3 py-2">Composite</th>
            <th className="text-left px-3 py-2">Verdikt</th>
            <th className="text-left px-3 py-2">Horizont</th>
            <th className="text-left px-3 py-2">Zóna</th>
            <th className="text-right px-3 py-2">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.ticker} className="border-b border-[#232735] hover:bg-[#1a1d27] cursor-pointer"
                onClick={() => onSelect(it.ticker)}>
              <td className="px-3 py-2 font-medium text-white">{it.ticker}
                {it.bubble_flag && <span className="text-red-400 ml-1">⚠</span>}
                {alerts[it.ticker] && <span className="ml-1 align-middle"><AlertMark title={alertTitle(alerts[it.ticker])} /></span>}</td>
              <td className="px-3 py-2 text-right text-gray-300">{it.valuation_score?.toFixed(0) ?? "—"}</td>
              <td className="px-3 py-2 text-right text-gray-300">{it.composite_score?.toFixed(0) ?? "—"}</td>
              <td className="px-3 py-2" style={{ color: VERDICT_COLOR[it.valuation_verdict ?? ""] ?? "#9ca3af" }}>
                {it.valuation_verdict ?? "—"}</td>
              <td className="px-3 py-2 text-gray-400">{it.horizon_verdict ?? "—"}</td>
              <td className="px-3 py-2" title={it.zone_note ?? undefined}
                  style={{ color: it.zone && it.zone_reliable !== false ? ZONE_COLOR[it.zone] : "#6b7280" }}>
                {it.zone ? zoneText(it) : "—"}
              </td>
              <td className="px-3 py-2 text-right text-gray-500">
                {it.confidence != null ? (it.confidence * 100).toFixed(0) + " %" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
