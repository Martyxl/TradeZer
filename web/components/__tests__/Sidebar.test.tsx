import { describe, it, expect, vi } from "vitest";

vi.mock("next/link", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: null, loading: false, logout: () => {} }) }));
vi.mock("@/components/SupportButton", () => ({ SupportButton: () => null }));

import { NAV_GROUPS } from "@/components/Sidebar";
import { planRank } from "@/lib/config";

describe("menu", () => {
  const group = (key: string) => NAV_GROUPS.find((g) => g.key === key)!.items.map((i) => i.label);

  it("rozděluje položky na Dashboard / Trading / Investice", () => {
    expect(group("home")).toEqual(["Dashboard"]);
    expect(new Set(group("trading"))).toEqual(new Set(["Deník", "Historie", "ORB Radar", "Statistiky"]));
    expect(new Set(group("invest"))).toEqual(new Set([
      "Investice", "Daně", "TRADEZER investuje", "Valuation Radar", "Discovery", "Smart Money", "Dark Pool"]));
  });

  it("zamčené pod vyšším plánem je v bloku vždy níž (tarif neklesá)", () => {
    for (const g of NAV_GROUPS) {
      const ranks = g.items.map((i) => planRank(i.tier));
      expect(ranks).toEqual([...ranks].sort((a, b) => a - b));
    }
    expect(group("trading").at(-1)).toBe("Statistiky");            // Trader až na konci
    expect(group("invest").slice(-3)).toEqual(["Discovery", "Smart Money", "Dark Pool"]); // Pro úplně dole
  });
});
