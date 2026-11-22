import { describe, it, expect, vi } from "vitest";

vi.mock("next/link", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push: () => {}, replace: () => {} }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: null, loading: false, logout: () => {} }), authHeaders: () => ({}) }));
vi.mock("@/components/SupportButton", () => ({ SupportButton: () => null }));

import { counterpartPath } from "@/lib/mode";
import { NAV_GROUPS, SIMPLE_GROUPS } from "@/components/Sidebar";

describe("přepínač Začátečník / Pokročilý", () => {
  it("převede stránku na odpovídající v druhém režimu", () => {
    expect(counterpartPath("/investice", "simple")).toBe("/investor/portfolio");
    expect(counterpartPath("/dane", "simple")).toBe("/investor/portfolio");
    expect(counterpartPath("/valuation", "simple")).toBe("/investor/napady");
    expect(counterpartPath("/fond", "simple")).toBe("/investor/fond");
    expect(counterpartPath("/denik", "simple")).toBe("/investor");          // trading začátečník nemá
    expect(counterpartPath("/investor/napady", "pro")).toBe("/valuation");
    expect(counterpartPath("/investor", "pro")).toBe("/dashboard");
    expect(counterpartPath("/investor/portfolio", "pro")).toBe("/investice");
  });

  it("sdílené stránky a stránky vlastního režimu nechá být", () => {
    expect(counterpartPath("/ucet", "simple")).toBe("/ucet");
    expect(counterpartPath("/legenda", "pro")).toBe("/legenda");
    expect(counterpartPath("/stats", "pro")).toBe("/stats");
    expect(counterpartPath("/investor/fond", "simple")).toBe("/investor/fond");
  });

  it("menu Začátečníka má 4 stránky a pokročilé menu se nezměnilo", () => {
    expect(SIMPLE_GROUPS.flatMap((g) => g.items.map((i) => i.label))).toEqual(
      ["Přehled", "Moje portfolio", "Nápady", "Tradezer investuje"]);
    expect(NAV_GROUPS.map((g) => g.key)).toEqual(["home", "trading", "invest"]);
    expect(NAV_GROUPS.flatMap((g) => g.items).some((i) => i.href.startsWith("/investor"))).toBe(false);
  });
});
