"use client";

import { useEffect, useState } from "react";
import { Target, LayoutGrid, Table2, Info } from "lucide-react";
import { BubbleMap, VERDICT_COLOR, type OverviewItem } from "@/components/valuation/BubbleMap";
import { ValuationDetail } from "@/components/valuation/ValuationDetail";

interface Group { key: string; label_cs: string; color_hex: string }

export default function ValuationPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [items, setItems] = useState<OverviewItem[]>([]);
  const [group, setGroup] = useState<string | null>(null);
  const [view, setView] = useState<"map" | "table">("map");
  const [selected, setSelected] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/valuation/groups", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null)).then((d) => setGroups(d?.groups ?? [])).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const q = group ? `?group=${group}` : "";
    fetch(`/api/valuation/overview${q}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setItems(d?.items ?? []); setAsOf(d?.meta?.as_of_date ?? null); })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [group]);

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
      </div>

      {loading ? (
        <div className="h-[460px] rounded-xl bg-[#151823] animate-pulse border border-[#2a2d3a]" />
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-yellow-800 bg-yellow-950/40 p-6 text-center text-sm text-yellow-300">
          <Info size={18} className="inline mb-1" /><br />
          Zatím nejsou k dispozici žádná skóre. Spusť ingest fundamentů a přepočet
          (<code className="text-yellow-200">make ingest &amp;&amp; make score</code>, nebo POST /api/valuation/refresh).
        </div>
      ) : view === "map" ? (
        <>
          <BubbleMap items={items} onSelect={setSelected} />
          <Legend />
        </>
      ) : (
        <ValuationTable items={items} onSelect={setSelected} />
      )}

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
      <span>velikost = tržní kapitalizace</span>
    </div>
  );
}

function ValuationTable({ items, onSelect }: { items: OverviewItem[]; onSelect: (t: string) => void }) {
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
            <th className="text-right px-3 py-2">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.ticker} className="border-b border-[#232735] hover:bg-[#1a1d27] cursor-pointer"
                onClick={() => onSelect(it.ticker)}>
              <td className="px-3 py-2 font-medium text-white">{it.ticker}
                {it.bubble_flag && <span className="text-red-400 ml-1">⚠</span>}</td>
              <td className="px-3 py-2 text-right text-gray-300">{it.valuation_score?.toFixed(0) ?? "—"}</td>
              <td className="px-3 py-2 text-right text-gray-300">{it.composite_score?.toFixed(0) ?? "—"}</td>
              <td className="px-3 py-2" style={{ color: VERDICT_COLOR[it.valuation_verdict ?? ""] ?? "#9ca3af" }}>
                {it.valuation_verdict ?? "—"}</td>
              <td className="px-3 py-2 text-gray-400">{it.horizon_verdict ?? "—"}</td>
              <td className="px-3 py-2 text-right text-gray-500">
                {it.confidence != null ? (it.confidence * 100).toFixed(0) + " %" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
