"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { Card } from "./ui";
import type { Bucket, Pillar } from "./types";

// Barvy skupin — třídy, které světlý motiv přemapuje (globals.css).
const BUCKET: Record<Bucket, { label: string; cls: string }> = {
  cheap: { label: "Levná", cls: "bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-500/40" },
  fair: { label: "Férová cena", cls: "bg-blue-950/50 text-blue-300" },
  expensive: { label: "Drahá", cls: "bg-red-950/50 text-red-300 ring-1 ring-inset ring-red-500/40" },
  unknown: { label: "Bez hodnocení", cls: "bg-raised text-gray-400" },
};

export function BucketPill({ bucket, label, big = false }: { bucket: Bucket; label?: string | null; big?: boolean }) {
  const b = BUCKET[bucket];
  return (
    <span className={`inline-flex items-center justify-center whitespace-nowrap rounded-full font-semibold ${b.cls} ${big ? "px-3 py-1 text-[13px]" : "w-full px-2 py-0.5 text-[11.5px]"}`}>
      {label || b.label}
    </span>
  );
}

const LEVEL: Record<Pillar["level"], { word: string; color: string }> = {
  good: { word: "Dobré", color: "#4ade80" }, ok: { word: "Průměr", color: "#f59e0b" },
  weak: { word: "Slabé", color: "#ef4444" }, none: { word: "Bez dat", color: "#6b7280" },
};

export function PillarCard({ p }: { p: Pillar }) {
  const l = LEVEL[p.level];
  return (
    <div className="rounded-xl border border-line bg-sunken p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-[11.5px] text-gray-500">{p.label}</div>
          <div className="text-[14px] font-semibold text-white">{p.question}</div>
        </div>
        <span className="flex shrink-0 items-center gap-1.5 text-[12.5px] font-semibold" style={{ color: l.color }}>
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />{l.word}
        </span>
      </div>
      {p.score != null && (
        <div className="mt-2 h-1.5 rounded-full bg-raised" title={`skóre ${Math.round(p.score)} / 100`}>
          <div className="h-full rounded-full" style={{ width: `${Math.max(3, p.score)}%`, background: l.color }} />
        </div>
      )}
      <p className="mt-2 text-[13px] leading-relaxed text-gray-300">{p.text}</p>
    </div>
  );
}

/** Radar je ve stejném tarifu jako plný Valuation Radar. */
export function PlanNeeded() {
  return (
    <Card className="text-center">
      <Lock size={20} className="mx-auto text-gray-500" />
      <p className="mt-2 text-sm text-gray-300">Radar firem je součástí tarifu <b className="text-white">Trader</b> — stejně jako Valuation Radar v režimu Pokročilý.</p>
      <Link href="/predplatne" className="mt-3 inline-block rounded-full bg-white px-4 py-2 text-sm font-semibold text-on-ink hover:bg-white/85">Zobrazit tarify</Link>
    </Card>
  );
}
