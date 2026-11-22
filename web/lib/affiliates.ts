// Odkazy na brokery v jednoduchém režimu (tlačítka „Koupit u XTB / eToro").
//
// Partnerské (affiliate) URL se NIKDY nepíší do kódu — nastav je na Vercelu:
//   NEXT_PUBLIC_AFF_XTB_URL    = partnerský odkaz z XTB Partners
//   NEXT_PUBLIC_AFF_ETORO_URL  = partnerský odkaz z eToro Partners
//   NEXT_PUBLIC_AFF_XTB_RISK / NEXT_PUBLIC_AFF_ETORO_RISK = přesné upozornění na riziko, které broker
//     vyžaduje u propagace (obsahuje aktuální % ztrátových retailových CFD účtů, mění se čtvrtletně).
// Bez nich vedou tlačítka na běžný web brokera a štítek „partnerský odkaz" se neukazuje.

export interface Broker {
  key: "xtb" | "etoro";
  name: string;
  url: string;
  affiliate: boolean;
  pitch: string;
  risk: string;
}

const GENERIC_RISK =
  "CFD jsou složité nástroje s vysokým rizikem rychlé ztráty peněz kvůli páce; většina účtů retailových investorů " +
  "při obchodování s CFD přichází o peníze. ETF a akcie kupuj jako skutečné cenné papíry, ne jako CFD.";

function broker(key: Broker["key"], name: string, fallback: string, envUrl: string | undefined,
                envRisk: string | undefined, pitch: string): Broker {
  const url = (envUrl || "").trim();
  return { key, name, url: url || fallback, affiliate: !!url, pitch, risk: (envRisk || "").trim() || GENERIC_RISK };
}

// process.env.NEXT_PUBLIC_* musí být zapsané doslova (Next je při buildu nahradí hodnotou).
export const BROKERS: Broker[] = [
  broker("xtb", "XTB", "https://www.xtb.com/cz", process.env.NEXT_PUBLIC_AFF_XTB_URL,
    process.env.NEXT_PUBLIC_AFF_XTB_RISK, "ETF a akcie bez poplatku do 100 000 € měsíčně, česká podpora, výpis pro daně."),
  broker("etoro", "eToro", "https://www.etoro.com/cs/", process.env.NEXT_PUBLIC_AFF_ETORO_URL,
    process.env.NEXT_PUBLIC_AFF_ETORO_RISK, "Jednoduchá aplikace, zlomky akcií, kopírování portfolií."),
];

export const ANY_AFFILIATE = BROKERS.some((b) => b.affiliate);
