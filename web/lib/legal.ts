// Právní údaje provozovatele + verze podmínek. JEDNO místo — používá VOP, Zásady, Cookies, patička.
//
// DOPLNIT před spuštěním plateb (viz TODO níže): kontaktní e-mail, stav plátce DPH.
// Při věcné změně VOP / Zásad zvyš `termsVersion` (musí odpovídat `TERMS_VERSION` v api/app/legal.py).

export const LEGAL = {
  name: "Martin Špatenka",
  ico: "88916219",
  address: "Kozomínská 611, Postřižín",
  // Kontaktní e-mail (reklamace, odstoupení, GDPR žádosti) — příjem ověřen přes Resend (2026-10-16). Prázdné = na webu
  // se zobrazí výrazná výzva „doplnit“, ať se na to nezapomene.
  email: "info@tradezer.app",
  // Plátce DPH (potvrzeno 2026-10-16). Po založení firmy přepsat údaje provozovatele níže.
  vatPayer: true as boolean | null,
  // TODO: DIČ provozovatele (plátce DPH ho uvádí na dokladech). U fyzické osoby NEMUSÍ být totéž co IČO.
  dic: "",
  site: "tradezer.app",
  termsVersion: "2026-10-15",
  effectiveFrom: "15. 10. 2026",
};

export const termsPending = LEGAL.email === "" || LEGAL.vatPayer === null || (LEGAL.vatPayer && LEGAL.dic === "");
