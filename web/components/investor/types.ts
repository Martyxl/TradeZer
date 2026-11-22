// Tvary dat z /api/investor/* (api/app/routers/investor.py).

export type ClassKey = "world" | "bonds" | "gold" | "cash" | "stocks";
export type PlanKey = "careful" | "balanced" | "bold" | "aggressive" | "custom";

export interface Profile {
  mode: "simple" | "pro" | null;
  plan: PlanKey;
  targets: Record<ClassKey, number>;
  custom_targets: Record<ClassKey, number> | null;
  monthly_czk: number;
  reserve_czk: number;
  capital_czk: number;        // zadané volné peníze k investování
  capital_left: number;       // kolik z nich zbývá po nákupech zapsaných od zadání
  capital_set_at: string | null;
  saved: boolean;
  plan_set: boolean;          // false = plán je jen výchozí, uživatel ho ještě nevybral
  plans: Record<Exclude<PlanKey, "custom">, { label: string; targets: Record<ClassKey, number>; for: string }>;
  classes: Record<ClassKey, string>;
}

export interface AllocRow { cls: ClassKey; label: string; value: number; pct: number; target: number; diff: number }

export type ActionKind = "buy" | "trim" | "wait" | "rebalance" | "tax" | "hold";
export interface Action {
  kind: ActionKind; title: string; text: string;
  symbol?: string | null; name?: string | null; cls?: ClassKey;
  amount?: number; units?: number | null; qty?: number | null; count?: number;
  price?: number; currency?: string | null;
}

export interface SimplePosition {
  symbol: string; name: string | null; cls: ClassKey; class_label: string;
  value: number | null; weight: number | null; unrealized_pct: number | null;
  tag: "buy" | "trim" | "wait" | "hold"; tax_free_from: string | null; tax_free_all: boolean; tax_free_part?: boolean;
}

export interface Market {
  regime: { state: string; label: string; tip: string; as_of?: string } | null;
  sentiment: { score: number | null; label: string; tip: string; as_of?: string } | null;
}

export interface Plan {
  profile: Profile;
  totals: { invested: number; value: number; unrealized: number; complete: boolean;
            tax_free: number; tax_pending: number; reserve: number };
  allocation: { total: number; classes: AllocRow[]; unpriced: string[] };
  contribution: { cls: ClassKey; label: string; amount: number }[];
  invest_now: { total: number; monthly: number; capital: number; hint: string | null };
  actions: Action[];
  positions: SimplePosition[];
  market: Market;
}

export interface Instrument {
  symbol: string; short: string; cls: ClassKey; class_label: string; name: string; what: string; role: string;
  ter: number; currency: string; held: boolean; default?: boolean;
  price: number | null; price_currency: string; price_czk: number | null;
  high_52w: number | null; low_52w: number | null;
}

export interface Idea {
  ticker: string; name: string | null; verdict: string | null; kind: "cheap" | "expensive";
  text: string; tags: string[]; score: number | null; market_cap: number | null;
}

export interface Ideas { base: Instrument[]; cheap: Idea[]; expensive: Idea[]; as_of: string | null }

export type Bucket = "cheap" | "fair" | "expensive" | "unknown";
export interface RadarItem {
  ticker: string; name: string | null; verdict: string | null; verdict_label: string | null; bucket: Bucket;
  zone: string | null; reliable: boolean; text: string; held: boolean; market_cap: number | null; score: number | null;
  pctile_pe_fwd: number | null; eps_growth_ntm: number | null; bubble_flag: boolean; confidence: number | null;
}
export interface Radar { as_of: string | null; items: RadarItem[]; zones: { buy: [number, number][]; sell: [number, number][] } | null }

export interface Pillar { key: string; label: string; question: string; score: number | null; level: "good" | "ok" | "weak" | "none"; text: string }
export interface Company {
  ticker: string; name: string | null; sector: string | null; industry: string | null; as_of: string | null;
  held: boolean; weight: number | null; next_earnings: string | null;
  verdict: string | null; verdict_label: string | null; bucket: Bucket; headline: string; overall: string | null;
  zone: string | null; reliable: boolean; reliability_note: string | null;
  pillars: Pillar[]; pros: string[]; cons: string[];
  advice: { kind: "buy" | "hold" | "wait" | "trim"; text: string };
}
