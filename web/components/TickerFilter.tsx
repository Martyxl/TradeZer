"use client";

import { cn } from "@/lib/utils";
import type { Ticker } from "@/lib/api";

interface TickerFilterProps {
  tickers: Ticker[];
  selected: string;
  onChange: (symbol: string) => void;
}

// Třída aktiva jako malá tečka (forex / komodity / krypto / futures), výběr jako segmentový přepínač.
const ASSET_DOT: Record<string, string> = {
  forex: "bg-sky-400",
  commodity: "bg-amber-300",
  crypto: "bg-orange-400",
  futures: "bg-violet-400",
};

export function TickerFilter({ tickers, selected, onChange }: TickerFilterProps) {
  return (
    <div role="group" aria-label="Instrument" className="inline-flex flex-wrap gap-0.5 rounded-full border border-line bg-raised p-1">
      {tickers.map((ticker) => {
        const isActive = ticker.symbol === selected;
        return (
          <button
            key={ticker.symbol}
            type="button"
            aria-pressed={isActive}
            title={ticker.name}
            onClick={() => onChange(ticker.symbol)}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors",
              isActive ? "bg-[#0a0f0d] text-white" : "text-gray-400 hover:text-white"
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", ASSET_DOT[ticker.asset_class] ?? ASSET_DOT.forex)} />
            {ticker.symbol}
          </button>
        );
      })}
    </div>
  );
}
