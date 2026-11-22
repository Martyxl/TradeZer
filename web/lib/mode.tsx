"use client";

// Režim aplikace: „simple" (Začátečník — 4 stránky pod /investor, jen signály a portfolio)
// vs. „pro" (Pokročilý — celá současná aplikace beze změn). Výchozí je pro, ať se stávajícím
// uživatelům nic nezmění. Volba se drží v localStorage (okamžitě, i bez přihlášení) a u
// přihlášeného i na účtu (/api/investor/profile), takže platí na všech zařízeních.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { authHeaders, useAuth } from "@/lib/auth";
import { beginnerModeAvailable } from "@/lib/config";

export type Mode = "simple" | "pro";
const KEY = "tz_mode";

/** Odpovídající stránka v druhém režimu (přepínač tě nechá „na stejném místě"). */
const TO_SIMPLE: [string, string][] = [
  ["/investice", "/investor/portfolio"], ["/dane", "/investor/portfolio"],
  ["/valuation", "/investor/napady"], ["/fond", "/investor/fond"],
];
const TO_PRO: [string, string][] = [
  ["/investor/portfolio", "/investice"], ["/investor/napady", "/valuation"], ["/investor/fond", "/fond"],
  ["/investor", "/dashboard"],
];
// Stránky, které jsou v obou režimech stejné (při přepnutí se z nich neodchází).
const SHARED = ["/ucet", "/predplatne", "/admin", "/legenda"];

export function counterpartPath(path: string, to: Mode): string {
  if (SHARED.some((p) => path.startsWith(p))) return path;
  if (to === "simple") {
    if (path.startsWith("/investor")) return path;
    return TO_SIMPLE.find(([from]) => path.startsWith(from))?.[1] ?? "/investor";
  }
  if (!path.startsWith("/investor")) return path;
  return TO_PRO.find(([from]) => path.startsWith(from))?.[1] ?? "/dashboard";
}

function readLocal(): Mode | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "simple" || v === "pro" ? v : null;
  } catch {
    return null;
  }
}
function writeLocal(m: Mode) {
  try { localStorage.setItem(KEY, m); } catch { /* soukromé okno — jen pro tuto relaci */ }
}

interface ModeState {
  mode: Mode;
  /** true = uživatel režim ještě nikdy nezvolil (ukázat volbu při prvním přihlášení). */
  unset: boolean;
  /** false do chvíle, než se přečte uložená volba (zabrání probliknutí menu). */
  ready: boolean;
  /** Smí uživatel režim Začátečník používat (config.BEGINNER_MODE)? Jinak vždy „pro" a bez přepínače. */
  available: boolean;
  setMode: (m: Mode, opts?: { navigate?: boolean }) => void;
}

const Ctx = createContext<ModeState | null>(null);

function saveRemote(m: Mode) {
  fetch("/api/investor/profile", {
    method: "PUT", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ mode: m }),
  }).catch(() => { /* lokální volba platí dál, příště se zkusí znovu */ });
}

export function ModeProvider({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mode, setModeState] = useState<Mode>("pro");
  const [unset, setUnset] = useState(false);
  const [ready, setReady] = useState(false);
  const synced = useRef<number | null>(null);
  const available = !loading && beginnerModeAvailable(user);

  // 1) lokální volba hned po mountu
  useEffect(() => {
    const l = readLocal();
    if (l) setModeState(l);
    setUnset(!l);
    setReady(true);
  }, []);

  // 2) přihlášený: účet má přednost; když účet volbu nemá a lokálně ano, nahraj ji na účet
  useEffect(() => {
    if (loading || !user || !available || synced.current === user.id) return;
    synced.current = user.id;
    fetch("/api/investor/profile", { headers: authHeaders(), cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((p: { mode: Mode | null } | null) => {
        if (!p) return;
        const l = readLocal();
        if (p.mode) {
          setModeState(p.mode); writeLocal(p.mode); setUnset(false);
        } else if (l) {
          saveRemote(l); setUnset(false);
        } else {
          setUnset(true);
        }
      })
      .catch(() => {});
  }, [user, loading, available]);

  // 3) Začátečník nemá Dashboard — přihlášení/odkazy na /dashboard vedou na jeho Přehled
  useEffect(() => {
    if (ready && available && mode === "simple" && pathname === "/dashboard") router.replace("/investor");
  }, [ready, available, mode, pathname, router]);

  const setMode = useCallback((m: Mode, opts?: { navigate?: boolean }) => {
    setModeState(m);
    setUnset(false);
    writeLocal(m);
    if (user) saveRemote(m);
    if (opts?.navigate !== false) {
      const target = counterpartPath(window.location.pathname, m);
      if (target !== window.location.pathname) router.push(target);
    }
  }, [user, router]);

  // Bez přístupu k režimu Začátečník se aplikace chová přesně jako dřív (menu Pokročilý, žádná volba).
  // Během načítání přihlášení `ready` drží false, ať menu nepřeblikne.
  const value: ModeState = available
    ? { mode, unset, ready, available, setMode }
    : { mode: "pro", unset: false, ready: ready && !loading, available: false, setMode: () => {} };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useMode(): ModeState {
  const c = useContext(Ctx);
  // Mimo provider (testy, stránky bez app layoutu) se chová jako dnešní aplikace.
  return c ?? { mode: "pro", unset: false, ready: true, available: false, setMode: () => {} };
}
