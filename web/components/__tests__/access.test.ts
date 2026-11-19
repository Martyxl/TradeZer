import { describe, it, expect } from "vitest";
import { FREE_ACCESS, hasAccess } from "@/lib/config";
import { FREE_ALL_FEATURES } from "@/lib/plans";

describe("přístup v režimu vše zdarma", () => {
  it("je zapnutý a odpovídá backendu (FREE_ACCESS)", () => expect(FREE_ACCESS).toBe(true));
  it("přihlášený má vše do Pro, Elite ne; anonym jen Free", () => {
    const u = { plan: "free", is_admin: false };
    expect(["free", "trader", "pro"].every((t) => hasAccess(u, t as never))).toBe(true);
    expect(hasAccess(u, "elite")).toBe(false);
    expect(hasAccess(null, "free")).toBe(true);
    expect(hasAccess(null, "trader")).toBe(false);
    expect(hasAccess({ plan: "free", is_admin: true }, "elite")).toBe(true);
  });
  it("seznam funkcí zdarma neobsahuje odkazy na plány ani ceny", () => {
    expect(FREE_ALL_FEATURES.length).toBeGreaterThan(6);
    expect(FREE_ALL_FEATURES.some((f) => /Vše z|\/ ?měs|předplat/i.test(f))).toBe(false);
  });
});
