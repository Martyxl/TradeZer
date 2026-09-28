// Sdílená definice plánů a modulů — používá /predplatne, /funkce i landing,
// ať je nabídka všude konzistentní. Ceny v USD, roční platba se slevou.

export const ANNUAL_DISCOUNT = 0.15; // 15 % sleva při roční platbě

export type TierId = "free" | "trader" | "pro";

export type TierId2 = TierId | "elite";

export interface Plan {
  id: TierId2;
  name: string;
  priceUsd: number;      // měsíční cena
  tagline: string;
  highlight?: boolean;   // zvýrazněná karta
  soon?: boolean;        // ještě nespuštěno (např. živá data)
  features: string[];
}

export const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    priceUsd: 0,
    tagline: "Začni zdarma, ihned",
    features: [
      "Dashboard: AI predikce dopadu zpráv, denní BIAS, Gamma režim a výhled",
      "Obchodní deník + AI čtení grafů z TradingView",
      "ORB Radar — statistiky opening range podle sessionů",
      "Historie a úspěšnost predikcí (90 dní zpětně)",
    ],
  },
  {
    id: "trader",
    name: "Trader",
    priceUsd: 5,
    tagline: "Pro aktivní tradery",
    highlight: true,
    features: [
      "Vše z Free",
      "Kompletní Statistiky — session ranges, pravděpodobnosti, NPOC a breaky",
      "Valuation Radar — fundamentální skóre firem ze SEC dat",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    priceUsd: 15,
    tagline: "Kompletní výbava",
    features: [
      "Vše z Trader",
      "Discovery — screener momentum příležitostí (<$50B) + katalyzátory",
      "Smart Money — insider aktivita ze SEC Form 4",
    ],
  },
  {
    id: "elite",
    name: "Elite",
    priceUsd: 49,
    tagline: "Živá data v reálném čase",
    soon: true,
    features: [
      "Vše z Pro",
      "Živá (real-time) data místo zpožděných",
      "Real-time options flow a gamma úrovně",
      "Okamžité alerty na zprávy a klíčové úrovně",
    ],
  },
];

// Hodnotová kotva — co by trader zaplatil za srovnatelné nástroje ZVLÁŠŤ.
export interface CompareRow { category: string; tool: string; priceUsd: number; }
export const COMPARISON: CompareRow[] = [
  { category: "Gamma / GEX levely", tool: "SpotGamma", priceUsd: 67 },
  { category: "Options flow + insider + congress", tool: "Unusual Whales", priceUsd: 50 },
  { category: "Momentum screener", tool: "Trade Ideas", priceUsd: 86 },
  { category: "Fundamentální valuace", tool: "Stock Rover", priceUsd: 29 },
  { category: "Obchodní deník", tool: "TradeZella", priceUsd: 35 },
  { category: "News / katalyzátory", tool: "Benzinga Pro", priceUsd: 37 },
];
export function comparisonTotal(): number {
  return COMPARISON.reduce((s, r) => s + r.priceUsd, 0);
}

// Roční cena za měsíc (se slevou) a celkem za rok.
export function annualPerMonth(priceUsd: number): number {
  return Math.round(priceUsd * (1 - ANNUAL_DISCOUNT) * 100) / 100;
}
export function annualTotal(priceUsd: number): number {
  return Math.round(priceUsd * 12 * (1 - ANNUAL_DISCOUNT)); // celé dolary
}

// ── Moduly (co všechno appka umí zobrazit) — pro /funkce a landing ──────────
export interface AppModule {
  name: string;
  tier: TierId;
  icon: string;      // lucide název (mapuje se ve /funkce)
  desc: string;
}

export const MODULES: AppModule[] = [
  { name: "Dashboard", tier: "free", icon: "LayoutDashboard",
    desc: "Živé AI predikce dopadu zpráv s pravděpodobností směru, denní BIAS, entry plán a denní výhled na plánované US eventy." },
  { name: "Gamma (GEX)", tier: "free", icon: "Activity",
    desc: "Dealer gamma z opčního OI (index opce ve futures škále): režim trhu (tlumený vs. trendový), flip level, call/put wall — s dynamickým čtením k aktuálnímu stavu." },
  { name: "Obchodní deník", tier: "free", icon: "NotebookPen",
    desc: "Ruční deník obchodů se statistikou (win rate, expektance, R) + AI vytěžení obchodu z TradingView grafu (instrument, směr, entry/target/stop)." },
  { name: "ORB Radar", tier: "free", icon: "Sunrise",
    desc: "Statistika opening range podle sessionů (Asia/London/NY) — jak často a v jakém horizontu se sundá high/low první svíčky, s plovoucím trendem." },
  { name: "Historie", tier: "free", icon: "History",
    desc: "Každá predikce vedle toho, co trh skutečně udělal — a úspěšnost černá na bílém, 90 dní zpětně." },
  { name: "Statistiky", tier: "trader", icon: "BarChart3",
    desc: "Kompletní tržní statistiky pro NQ a GOLD — session ranges, pravděpodobnosti, revisity open/NPOC, oboustranné breaky. Podklad pro obchodní pravidla." },
  { name: "Valuation Radar", tier: "trader", icon: "Target",
    desc: "Fundamentální skórování firem ze SEC dat — P/E percentil, ROIC, marže, růst, verdikt LEVNÁ/FÉROVÁ/PŘEPÁLENÁ. Bublinová mapa sektorů." },
  { name: "Discovery", tier: "pro", icon: "Telescope",
    desc: "Screener krátkodobých momentum příležitostí napříč small/mid-cap univerzem (<$50B) — momentum, relativní objem, katalyzátory (earnings)." },
  { name: "Smart Money", tier: "pro", icon: "Landmark",
    desc: "Insider aktivita ze SEC Form 4 — kdo z vedení firem nakupoval a prodával vlastní akcie, s hodnotou obchodů a žebříčkem nákupů." },
  { name: "Legenda", tier: "free", icon: "BookOpen",
    desc: "Vysvětlivky všech pojmů, zkratek a výpočtů použitých v aplikaci — s vyhledáváním a návodem, jak číst gamma." },
];
