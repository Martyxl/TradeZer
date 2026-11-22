"use client";

import { useCallback, useEffect, useState } from "react";
import { authHeaders, useAuth } from "@/lib/auth";
import type { Ideas, Plan, Profile } from "./types";

/** Načte JSON z přihlášeného API; `reload()` po změně (nový nákup, jiný plán). */
function useAuthed<T>(url: string): { data: T | null; error: boolean; loading: boolean; reload: () => Promise<void> } {
  const { user } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const r = await fetch(url, { headers: authHeaders(), cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      setData(await r.json());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [url, user]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload };
}

export const usePlan = () => useAuthed<Plan>("/api/investor/plan");
export const useIdeas = () => useAuthed<Ideas>("/api/investor/ideas");

export async function saveProfile(patch: Partial<Pick<Profile, "plan" | "monthly_czk" | "reserve_czk">> & { targets?: Record<string, number> }): Promise<Profile> {
  const r = await fetch("/api/investor/profile", {
    method: "PUT", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(patch),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || "Uložení se nepodařilo");
  return d as Profile;
}

export const fmtCzk = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v).toLocaleString("cs-CZ")} Kč`;

export const fmtPct = (v: number | null | undefined, sign = true) =>
  v == null ? "—" : `${sign && v > 0 ? "+" : ""}${v.toLocaleString("cs-CZ", { maximumFractionDigits: 1 })} %`;

export const dateCs = (iso: string | null | undefined) =>
  iso ? new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString("cs-CZ") : "—";

/** Odhad měny podle burzovního suffixu (předvyplnění nákupu). */
export function guessCurrency(symbol: string | null | undefined): string {
  const s = (symbol || "").toUpperCase();
  if (/\.(DE|F|AS|PA|MI|NL|NV)$/.test(s)) return "EUR";
  if (/\.(L|LN|UK)$/.test(s)) return "USD";
  if (/\.PR$/.test(s)) return "CZK";
  return "USD";
}
