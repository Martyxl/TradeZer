// Gated route pro Statistiky (Trader+). Full stats JSON leží MIMO web/public
// (web/stats-src), takže nejde stáhnout přímou URL — servíruje se jen s dostatečným
// plánem. Ověření plánu = server-to-server dotaz na backend /api/auth/me.
import { NextRequest, NextResponse } from "next/server";
import nq from "@/stats-src/nq.json";
import gold from "@/stats-src/gold.json";
import ym from "@/stats-src/ym.json";

export const dynamic = "force-dynamic";

const FILES: Record<string, unknown> = { nq, gold, ym };
const RANK: Record<string, number> = { free: 0, trader: 1, pro: 2, elite: 3 };

async function entitled(req: NextRequest, min = "trader"): Promise<number> {
  // 0 = ok, jinak HTTP status (401/403)
  const auth = req.headers.get("authorization");
  if (!auth) return 401;
  const base = process.env.API_URL || "http://localhost:8000";
  try {
    const r = await fetch(`${base}/api/auth/me`, { headers: { Authorization: auth }, cache: "no-store" });
    if (!r.ok) return 401;
    const u = await r.json();
    if (u.is_admin) return 0;
    if ((RANK[(u.plan ?? "free").toLowerCase()] ?? 0) >= RANK[min]) return 0;
    return 403;
  } catch {
    return 401;
  }
}

export async function GET(req: NextRequest) {
  const ticker = (req.nextUrl.searchParams.get("ticker") || "").toLowerCase();
  const data = FILES[ticker];
  if (!data) return NextResponse.json({ error: "unknown ticker" }, { status: 404 });
  const gate = await entitled(req, "trader");
  if (gate !== 0) return NextResponse.json({ error: "forbidden" }, { status: gate });
  return NextResponse.json(data);
}

// redeploy trigger 2026-09-29
