/** Barevné varianty přihlášené aplikace. Hodnoty barev jsou v globals.css (html[data-tz-theme]). */
export const THEMES = [
  { key: "sklo", label: "Sklo", mode: "dark", swatch: ["#0a1a16", "#6fe0b0"] },
  { key: "grafit", label: "Grafit", mode: "dark", swatch: ["#1b1e20", "#5fe0c8"] },
  { key: "jantar", label: "Jantar", mode: "dark", swatch: ["#1a1613", "#ff7a45"] },
  { key: "den", label: "Den", mode: "light", swatch: ["#e9edeb", "#0f9f78"] },
  { key: "limetka", label: "Limetka", mode: "light", swatch: ["#e8e9e2", "#c6ec2e"] },
] as const;
export type ThemeKey = (typeof THEMES)[number]["key"];
export const THEME_STORAGE_KEY = "tz_theme";

/** Inline skript na začátek layoutu: nastaví motiv ještě před vykreslením (bez probliknutí). */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");var m=${JSON.stringify(
  Object.fromEntries(THEMES.map((t) => [t.key, t.mode])),
)};if(!m[t])t="sklo";var d=document.documentElement;d.dataset.tzTheme=t;d.dataset.tzMode=m[t];}catch(e){}})();`;
