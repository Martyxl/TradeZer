"use client";

import { cn } from "@/lib/utils";
import type { Ticker } from "@/lib/api";

interface TickerFilterProps {
  tickers: Ticker[];
  selected: string;
  onChange: (symbol: string) => void;
}

const ASSET_COLORS: Record<string, string> = {
  forex: "border-blue-700 data-[active=true]:bg-blue-700 data-[active=true]:text-white",
  commodity: "border-yellow-700 data-[active=true]:bg-yellow-700 data-[active=true]:text-white",
  crypto: "border-orange-700 data-[active=true]:bg-orange-700 data-[active=true]:text-white",
  futures: "border-purple-700 data-[active=true]:bg-purple-700 data-[active=true]:text-white",
};

export function TickerFilter({ tickers, selected, onChange }: TickerFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {tickers.map((ticker) => {
        const colorClass = ASSET_COLORS[ticker.asset_class] ?? ASSET_COLORS.forex;
        const isActive = ticker.symbol === selected;
        return (
          <button
            key={ticker.symbol}
            data-active={isActive}
            onClick={() => onChange(ticker.symbol)}
            className={cn(
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-all",
              "text-gray-300 hover:text-white",
              colorClass,
              isActive ? "opacity-100" : "opacity-60 hover:opacity-80"
            )}
          >
            {ticker.symbol}
          </button>
        );
      })}
    </div>
  );
}
