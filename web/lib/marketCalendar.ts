/**
 * Kalendář zavřených a zkrácených dnů burz pro lištu sessions na Dashboardu.
 *
 * Data podle oficiálních kalendářů burz (NYSE, LSE, JPX, ASX) na 2026–2027.
 * Datum = místní datum dané burzy. Víkendy se řeší zvlášť (sobota/neděle = zavřeno).
 * Po roce 2027 je potřeba seznam doplnit — `calendarCovers()` to hlídá.
 */

export type MarketName = "Sydney" | "Tokyo" | "London" | "New York";

type DayMap = Record<string, string>;

/** Celodenní zavření: datum → název svátku. */
export const HOLIDAYS: Record<MarketName, DayMap> = {
  "New York": {
    "2026-01-01": "Nový rok", "2026-01-19": "Den M. L. Kinga", "2026-02-16": "Den prezidentů",
    "2026-04-03": "Velký pátek", "2026-05-25": "Memorial Day", "2026-06-19": "Juneteenth",
    "2026-07-03": "Den nezávislosti", "2026-09-07": "Labor Day", "2026-11-26": "Díkůvzdání",
    "2026-12-25": "Vánoce",
    "2027-01-01": "Nový rok", "2027-01-18": "Den M. L. Kinga", "2027-02-15": "Den prezidentů",
    "2027-03-26": "Velký pátek", "2027-05-31": "Memorial Day", "2027-06-18": "Juneteenth",
    "2027-07-05": "Den nezávislosti", "2027-09-06": "Labor Day", "2027-11-25": "Díkůvzdání",
    "2027-12-24": "Vánoce",
  },
  London: {
    "2026-01-01": "Nový rok", "2026-04-03": "Velký pátek", "2026-04-06": "Velikonoční pondělí",
    "2026-05-04": "Bank holiday", "2026-05-25": "Bank holiday", "2026-08-31": "Bank holiday",
    "2026-12-25": "Vánoce", "2026-12-28": "Boxing Day",
    "2027-01-01": "Nový rok", "2027-03-26": "Velký pátek", "2027-03-29": "Velikonoční pondělí",
    "2027-05-03": "Bank holiday", "2027-05-31": "Bank holiday", "2027-08-30": "Bank holiday",
    "2027-12-27": "Vánoce", "2027-12-28": "Boxing Day",
  },
  Tokyo: {
    "2026-01-01": "Nový rok", "2026-01-02": "Nový rok", "2026-01-12": "Den dospělosti",
    "2026-02-11": "Den založení státu", "2026-02-23": "Císařovy narozeniny", "2026-03-20": "Jarní rovnodennost",
    "2026-04-29": "Den Šówa", "2026-05-04": "Zlatý týden", "2026-05-05": "Zlatý týden", "2026-05-06": "Zlatý týden",
    "2026-07-20": "Den moře", "2026-08-11": "Den hor", "2026-09-21": "Den úcty ke stáří",
    "2026-09-22": "Státní svátek", "2026-09-23": "Podzimní rovnodennost", "2026-10-12": "Den sportu",
    "2026-11-03": "Den kultury", "2026-11-23": "Den díků za práci", "2026-12-31": "Konec roku",
    "2027-01-01": "Nový rok", "2027-01-11": "Den dospělosti", "2027-02-11": "Den založení státu",
    "2027-02-23": "Císařovy narozeniny", "2027-03-22": "Jarní rovnodennost", "2027-04-29": "Den Šówa",
    "2027-05-03": "Zlatý týden", "2027-05-04": "Zlatý týden", "2027-05-05": "Zlatý týden",
    "2027-07-19": "Den moře", "2027-08-11": "Den hor", "2027-09-20": "Den úcty ke stáří",
    "2027-09-23": "Podzimní rovnodennost", "2027-10-11": "Den sportu", "2027-11-03": "Den kultury",
    "2027-11-23": "Den díků za práci", "2027-12-31": "Konec roku",
  },
  Sydney: {
    "2026-01-01": "Nový rok", "2026-01-26": "Den Austrálie", "2026-04-03": "Velký pátek",
    "2026-04-06": "Velikonoční pondělí", "2026-06-08": "Královy narozeniny",
    "2026-12-25": "Vánoce", "2026-12-28": "Boxing Day",
    "2027-01-01": "Nový rok", "2027-01-26": "Den Austrálie", "2027-03-26": "Velký pátek",
    "2027-03-29": "Velikonoční pondělí", "2027-06-14": "Královy narozeniny",
    "2027-12-27": "Vánoce", "2027-12-28": "Boxing Day",
  },
};

/** Zkrácené dny: datum → [hodina zavření v místním čase burzy, popis]. */
export const EARLY_CLOSE: Partial<Record<MarketName, Record<string, [number, string]>>> = {
  "New York": {
    "2026-11-27": [13, "den po Díkůvzdání"], "2026-12-24": [13, "Štědrý den"],
    "2027-11-26": [13, "den po Díkůvzdání"],
  },
  London: {
    "2026-12-24": [12.5, "Štědrý den"], "2026-12-31": [12.5, "Silvestr"],
    "2027-12-24": [12.5, "Štědrý den"], "2027-12-31": [12.5, "Silvestr"],
  },
};

const COVERED_UNTIL = "2027-12-31";

/** Místní datum (YYYY-MM-DD) okamžiku `d` v časové zóně `tz`. */
export function localDate(tz: string, d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

function weekday(date: string): number {
  return new Date(`${date}T12:00:00Z`).getUTCDay();
}

export interface DayStatus {
  closed: boolean;
  /** Důvod zavření: název svátku, nebo „víkend". */
  reason?: string;
  /** Zkrácený den: hodina zavření v místním čase burzy. */
  earlyClose?: number;
  earlyReason?: string;
}

/** Stav burzy pro její místní datum `date`. */
export function dayStatus(market: MarketName, date: string): DayStatus {
  const wd = weekday(date);
  if (wd === 0 || wd === 6) return { closed: true, reason: "víkend" };
  const h = HOLIDAYS[market][date];
  if (h) return { closed: true, reason: h };
  const e = EARLY_CLOSE[market]?.[date];
  return e ? { closed: false, earlyClose: e[0], earlyReason: e[1] } : { closed: false };
}

export function calendarCovers(date: string): boolean {
  return date <= COVERED_UNTIL;
}

export interface UpcomingDay {
  market: MarketName;
  date: string;
  closed: boolean;
  label: string;
  /** Hodina zavření v místním čase burzy (jen zkrácené dny). */
  earlyClose?: number;
}

/** Svátky a zkrácené dny (bez víkendů) od `from` včetně na `days` dní dopředu, seřazené podle data. */
export function upcomingSpecialDays(from: string, days = 14, markets: MarketName[] = ["New York", "London", "Tokyo", "Sydney"]): UpcomingDay[] {
  const start = new Date(`${from}T12:00:00Z`).getTime();
  const out: UpcomingDay[] = [];
  for (let i = 0; i < days; i++) {
    const date = new Date(start + i * 86_400_000).toISOString().slice(0, 10);
    for (const m of markets) {
      const h = HOLIDAYS[m][date];
      if (h && weekday(date) % 6 !== 0) out.push({ market: m, date, closed: true, label: h });
      const e = EARLY_CLOSE[m]?.[date];
      if (e) out.push({ market: m, date, closed: false, label: e[1], earlyClose: e[0] });
    }
  }
  return out;
}
