import { describe, it, expect, vi, beforeEach } from "vitest";
import { dashFetch, invalidateDashboard } from "@/lib/dashboardData";

const AGG = {
  ticker: "NQ", errors: [] as string[],
  tickers: [{ symbol: "NQ" }], regime: { state: "calm" }, events_today: [],
  news: [{ id: 1 }], summary: null, bias_today: { ticker: "NQ" },
  bias_stats_30: { n: 30 }, bias_stats_90: { n: 90 }, gamma: { ticker: "NQ", instrument: null },
};

function mockFetch(handler: (url: string) => Response | Promise<Response>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => handler(String(input)));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const ok = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status });
const dashboardCalls = (fn: ReturnType<typeof vi.fn>) =>
  fn.mock.calls.filter((c) => String(c[0]).includes("/api/dashboard")).length;

beforeEach(() => { invalidateDashboard(); vi.unstubAllGlobals(); });

describe("dashFetch", () => {
  it("obslouží všech ~11 původních volání JEDNÍM požadavkem na /api/dashboard", async () => {
    const f = mockFetch((u) => (u.includes("/api/dashboard") ? ok(AGG) : ok({ unexpected: u }, 500)));
    const urls = ["/api/tickers", "/api/regime", "/api/news/events/today",
      "/api/news?ticker=NQ&limit=25&offset=0", "/api/bias/today?ticker=NQ",
      "/api/bias/stats?ticker=NQ&days=30", "/api/bias/stats?ticker=NQ&days=90", "/api/gamma?ticker=NQ"];
    const res = await Promise.all(urls.map((u) => dashFetch(u)));
    expect(res.every((r) => r.ok)).toBe(true);
    expect(await res[0].json()).toEqual(AGG.tickers);
    expect(await res[5].json()).toEqual({ n: 30 });
    expect(await res[6].json()).toEqual({ n: 90 });
    expect(f).toHaveBeenCalledTimes(1);               // jediné síťové volání
    expect(dashboardCalls(f)).toBe(1);
  });

  it("chybějící denní summary (null bez chyby) = 404 jako původní endpoint, bez dalšího volání", async () => {
    const f = mockFetch(() => ok(AGG));
    const r = await dashFetch("/api/summary/daily?ticker=NQ");
    expect(r.status).toBe(404);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("když část při sestavení selhala, zeptá se původního endpointu (ne falešná 404)", async () => {
    const f = mockFetch((u) => (u.includes("/api/dashboard") ? ok({ ...AGG, errors: ["summary: RuntimeError"] }) : ok({ real: true })));
    const r = await dashFetch("/api/summary/daily?ticker=NQ");
    expect(await r.json()).toEqual({ real: true });
    expect(f.mock.calls.at(-1)![0]).toBe("/api/summary/daily?ticker=NQ");
  });

  it("agregát selže (500/síť) → původní endpointy fungují jako dřív", async () => {
    mockFetch((u) => (u.includes("/api/dashboard") ? ok({}, 500) : ok({ direct: u })));
    const r = await dashFetch("/api/bias/today?ticker=NQ");
    expect(await r.json()).toEqual({ direct: "/api/bias/today?ticker=NQ" });
    vi.stubGlobal("fetch", vi.fn(async (u: string) => { if (u.includes("/api/dashboard")) throw new Error("net"); return ok({ direct: 1 }); }));
    invalidateDashboard();
    expect(await (await dashFetch("/api/gamma?ticker=NQ")).json()).toEqual({ direct: 1 });
  });

  it("neznámé cesty a jiné parametry jdou přímo (news s datem, jiný limit, historie…)", async () => {
    const f = mockFetch((u) => ok({ direct: u }));
    for (const u of ["/api/history?ticker=NQ&days=90", "/api/news?ticker=NQ&limit=10&offset=0",
      "/api/news?ticker=NQ&limit=25&offset=25", "/api/news?ticker=NQ&limit=25&offset=0&date=2026-10-01",
      "/api/bias/stats?ticker=NQ&days=7"]) {
      expect(await (await dashFetch(u)).json()).toEqual({ direct: u });
    }
    expect(dashboardCalls(f)).toBe(0);
  });

  it("paměť 30 s: druhé načtení nevolá znovu; po invalidaci ano", async () => {
    const f = mockFetch(() => ok(AGG));
    await dashFetch("/api/bias/today?ticker=NQ");
    await dashFetch("/api/gamma?ticker=NQ");
    expect(f).toHaveBeenCalledTimes(1);
    invalidateDashboard();
    await dashFetch("/api/gamma?ticker=NQ");
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("jiný ticker = vlastní agregát", async () => {
    const f = mockFetch((u) => ok({ ...AGG, ticker: new URL(u, "http://x").searchParams.get("ticker") }));
    await dashFetch("/api/bias/today?ticker=NQ");
    await dashFetch("/api/bias/today?ticker=XAUUSD");
    expect(f.mock.calls.map((c) => String(c[0]))).toEqual(["/api/dashboard?ticker=NQ", "/api/dashboard?ticker=XAUUSD"]);
  });
});
