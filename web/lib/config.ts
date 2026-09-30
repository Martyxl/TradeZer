// Feature flags + plánové tiery pro UI gate.
//
// PAYWALL_ENABLED=true → Free/nedostatečný plán uvidí upsell místo obsahu.
// SECURITY: skutečné vynucení je SERVER-SIDE (backend vrací 403 bez dostatečného
// plánu) — tento flag řídí jen UX (upsell místo prázdné/403 stránky).
export const PAYWALL_ENABLED = true;

export type Tier = "free" | "trader" | "pro" | "elite";

export const PLAN_RANK: Record<string, number> = { free: 0, trader: 1, pro: 2, elite: 3 };

export function planRank(plan: string | null | undefined): number {
  return PLAN_RANK[(plan ?? "free").toLowerCase()] ?? 0;
}

// Popis plánu pro upsell hlášku.
export const TIER_LABEL: Record<Tier, string> = {
  free: "Free", trader: "Trader ($5)", pro: "Pro ($15)", elite: "Elite ($49)",
};
