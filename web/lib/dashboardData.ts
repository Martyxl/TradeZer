// Dashboard: JEDEN agregovaný požadavek (/api/dashboard) místo ~11 samostatných volání.
//
// Proč: každé volání při studeném startu probudilo vlastní instanci funkce + DB spojení (až 16 s).
// Karty dál volají své původní URL přes `dashFetch` — ten je obslouží z jedné sdílené odpovědi
// (stejný tvar dat, takže komponenty se nemění). Cokoli, co agregát neumí nebo když selže,
// spadne bezpečně na původní endpoint (žádná regrese oproti dřívějšímu chování).

export const DEFAULT_TICKER = "NQ";
const TTL_MS = 30_000;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Agg = Record<string, any>;
const memo = new Map<string, { at: number; p: Promise<Agg | null> }>();

/** Po ručním refreshi zpráv zahodí sdílenou odpověď, ať se načtou čerstvá data. */
export function invalidateDashboard(): void {
  memo.clear();
}

export function loadDashboard(ticker: string, origin = ""): Promise<Agg | null> {
  const key = `${origin}|${ticker.toUpperCase()}`;
  const hit = memo.get(key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.p;
  const p: Promise<Agg | null> = fetch(`${origin}/api/dashboard?ticker=${encodeURIComponent(ticker.toUpperCase())}`)
    .then((r) => (r.ok ? (r.json() as Promise<Agg>) : null))
    .catch(() => null);
  memo.set(key, { at: Date.now(), p });
  p.then((v) => { if (!v) memo.delete(key); }); // neúspěch se nepamatuje → další volání zkusí znovu
  return p;
}

interface Route { ticker: string; pick: (a: Agg) => unknown; part: string }

/** Které původní URL umí agregát obsloužit (a z které jeho části). */
function route(u: URL): Route | null {
  const p = u.pathname;
  const q = u.searchParams;
  const t = (q.get("ticker") || "").toUpperCase();
  if (p === "/api/tickers") return { ticker: DEFAULT_TICKER, part: "tickers", pick: (a) => a.tickers };
  if (p === "/api/regime") return { ticker: DEFAULT_TICKER, part: "regime", pick: (a) => a.regime };
  if (p === "/api/news/events/today" && !q.get("date"))
    return { ticker: DEFAULT_TICKER, part: "events_today", pick: (a) => a.events_today };
  if (!t) return null;
  if (p === "/api/news" && !q.get("date") && q.get("limit") === "25" && (q.get("offset") ?? "0") === "0")
    return { ticker: t, part: "news", pick: (a) => a.news };
  if (p === "/api/summary/daily" && !q.get("date")) return { ticker: t, part: "summary", pick: (a) => a.summary };
  if (p === "/api/bias/today") return { ticker: t, part: "bias_today", pick: (a) => a.bias_today };
  if (p === "/api/bias/stats") {
    const d = q.get("days");
    if (d === "30") return { ticker: t, part: "bias_stats_30", pick: (a) => a.bias_stats_30 };
    if (d === "90") return { ticker: t, part: "bias_stats_90", pick: (a) => a.bias_stats_90 };
    return null;
  }
  if (p === "/api/gamma") return { ticker: t, part: "gamma", pick: (a) => a.gamma };
  return null;
}

const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status, headers: { "content-type": "application/json" } });

/** Drop-in náhrada `fetch` pro dashboardové karty. */
export async function dashFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    const u = new URL(url, window.location.origin);
    const r = route(u);
    if (r) {
      const agg = await loadDashboard(r.ticker, u.origin === window.location.origin ? "" : u.origin);
      if (agg) {
        const v = r.pick(agg);
        if (v !== undefined && v !== null) return json(v);
        // null = „data neexistují" (404) — ale ne když ta část při sestavení selhala (pak původní endpoint)
        const failed = (agg.errors as string[] | undefined)?.some((e) => e.startsWith(r.part));
        if (r.part === "summary" && !failed) return json({ detail: "Summary pro tento den neexistuje" }, 404);
      }
    }
  } catch {
    /* cokoli se pokazí → původní chování níže */
  }
  return fetch(url, init);
}
