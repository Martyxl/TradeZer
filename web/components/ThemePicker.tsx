"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Palette } from "lucide-react";

import { THEMES, THEME_STORAGE_KEY as STORAGE_KEY, type ThemeKey } from "@/lib/theme";

function applyTheme(key: ThemeKey) {
  const t = THEMES.find((x) => x.key === key) ?? THEMES[0];
  const d = document.documentElement;
  d.dataset.tzTheme = t.key;
  d.dataset.tzMode = t.mode;
  try { localStorage.setItem(STORAGE_KEY, t.key); } catch { /* soukromé okno apod. */ }
}

function useTheme(): [ThemeKey, (k: ThemeKey) => void] {
  const [theme, setTheme] = useState<ThemeKey>("sklo");
  useEffect(() => {
    const cur = document.documentElement.dataset.tzTheme as ThemeKey | undefined;
    if (cur && THEMES.some((t) => t.key === cur)) setTheme(cur);
  }, []);
  return [theme, (k) => { applyTheme(k); setTheme(k); }];
}

function Swatch({ colors, size = 18 }: { colors: readonly string[]; size?: number }) {
  return (
    <span aria-hidden className="relative inline-block shrink-0 overflow-hidden rounded-full border border-white/20"
      style={{ width: size, height: size, background: colors[0] }}>
      <span className="absolute bottom-0 right-0 rounded-full"
        style={{ width: size * 0.55, height: size * 0.55, background: colors[1] }} />
    </span>
  );
}

/** Přepínač v horní liště: tlačítko s paletou a rozbalovací seznam motivů. */
export function ThemePicker() {
  const [theme, setTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  const current = THEMES.find((t) => t.key === theme) ?? THEMES[0];
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu"
        title="Barevný motiv" aria-label={`Barevný motiv: ${current.label}`}
        className="flex h-10 items-center gap-2 rounded-full border border-line bg-panel px-3 text-sm text-gray-300 transition-colors hover:text-white">
        <Palette size={15} />
        <span className="hidden xl:inline">{current.label}</span>
        <Swatch colors={current.swatch} size={16} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-12 z-50 w-52 rounded-2xl border border-line bg-dialog p-1.5 shadow-2xl">
          <div className="px-2.5 pb-1.5 pt-1 text-[11.5px] font-semibold text-gray-500">Barevný motiv</div>
          {THEMES.map((t) => (
            <button key={t.key} type="button" role="menuitemradio" aria-checked={t.key === theme}
              onClick={() => { setTheme(t.key); setOpen(false); }}
              className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm transition-colors hover:bg-panel ${
                t.key === theme ? "text-white" : "text-gray-300"}`}>
              <Swatch colors={t.swatch} />
              <span className="flex-1">{t.label}</span>
              <span className="text-[11px] text-gray-500">{t.mode === "light" ? "světlý" : "tmavý"}</span>
              {t.key === theme ? <Check size={14} className="text-mint" /> : <span className="w-[14px]" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Kompaktní řada vzorků pro mobilní menu. */
export function ThemeSwatches() {
  const [theme, setTheme] = useTheme();
  return (
    <div role="radiogroup" aria-label="Barevný motiv" className="flex items-center gap-2 px-3">
      <span className="mr-auto text-[11.5px] font-semibold text-gray-500">Motiv</span>
      {THEMES.map((t) => (
        <button key={t.key} type="button" role="radio" aria-checked={t.key === theme} title={t.label}
          onClick={() => setTheme(t.key)}
          className={`grid h-9 w-9 place-items-center rounded-full border ${t.key === theme ? "border-mint" : "border-transparent"}`}>
          <Swatch colors={t.swatch} size={24} />
        </button>
      ))}
    </div>
  );
}
