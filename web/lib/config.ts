// Feature flags + plánové tiery pro UI gate.
//
// PAYWALL_ENABLED=true → Free/nedostatečný plán uvidí upsell místo obsahu.
// SECURITY: skutečné vynucení je SERVER-SIDE (backend vrací 403 bez dostatečného
// plánu) — tento flag řídí jen UX (upsell místo prázdné/403 stránky).
export const PAYWALL_ENABLED = true;

// Vše zdarma (start bez plateb, musí sedět s FREE_ACCESS na backendu): každý přihlášený má
// všechno do úrovně Pro, ceny a předplatné se nikde neukazují. Elite zůstává zašedlá ukázka.
export const FREE_ACCESS = true;

/** Má (ne)přihlášený uživatel přístup k modulu daného plánu? */
export function hasAccess(user: { plan?: string | null; is_admin?: boolean } | null | undefined, tier: Tier): boolean {
  if (user?.is_admin || !PAYWALL_ENABLED) return true;
  if (FREE_ACCESS && tier !== "elite") return tier === "free" || !!user;
  return planRank(user?.plan) >= planRank(tier);
}

export type Tier = "free" | "trader" | "pro" | "elite";

export const PLAN_RANK: Record<string, number> = { free: 0, trader: 1, pro: 2, elite: 3 };

export function planRank(plan: string | null | undefined): number {
  return PLAN_RANK[(plan ?? "free").toLowerCase()] ?? 0;
}

// Popis plánu pro upsell hlášku.
export const TIER_LABEL: Record<Tier, string> = {
  free: "Free", trader: "Trader ($5)", pro: "Pro ($15)", elite: "Elite ($49)",
};
