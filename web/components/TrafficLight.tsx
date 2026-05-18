"use client";

import { cn } from "@/lib/utils";

interface TrafficLightProps {
  probs: { down: number; neutral: number; up: number };
  size?: "sm" | "md" | "lg";
  showLabels?: boolean;
}

const SIZE = {
  sm: { circle: "w-5 h-5", gap: "gap-1", text: "text-xs" },
  md: { circle: "w-7 h-7", gap: "gap-1.5", text: "text-xs" },
  lg: { circle: "w-10 h-10", gap: "gap-2", text: "text-sm" },
};

interface LightProps {
  active: boolean;
  color: "down" | "neutral" | "up";
  pct: number;
  sizeClass: string;
}

function Light({ active, color, pct, sizeClass }: LightProps) {
  const colors = {
    down: {
      active: "bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.8)]",
      dim: "bg-red-950 border border-red-800",
    },
    neutral: {
      active: "bg-yellow-400 shadow-[0_0_12px_rgba(234,179,8,0.8)]",
      dim: "bg-yellow-950 border border-yellow-800",
    },
    up: {
      active: "bg-green-500 shadow-[0_0_12px_rgba(34,197,94,0.8)]",
      dim: "bg-green-950 border border-green-800",
    },
  };

  return (
    <div className="group relative flex items-center justify-center">
      <div
        className={cn(
          "rounded-full transition-all duration-300",
          sizeClass,
          active ? colors[color].active : colors[color].dim
        )}
        title={`${(pct * 100).toFixed(1)}%`}
      />
      {/* Tooltip on hover */}
      <span className="pointer-events-none absolute left-full ml-2 hidden whitespace-nowrap rounded bg-gray-800 px-1.5 py-0.5 text-xs text-white group-hover:block z-10">
        {(pct * 100).toFixed(1)}%
      </span>
    </div>
  );
}

export function TrafficLight({ probs, size = "md", showLabels = false }: TrafficLightProps) {
  const { circle, gap, text } = SIZE[size];
  const max = Math.max(probs.down, probs.neutral, probs.up);

  return (
    <div className={cn("flex flex-col items-center", gap)}>
      <Light active={probs.up === max} color="up" pct={probs.up} sizeClass={circle} />
      <Light active={probs.neutral === max} color="neutral" pct={probs.neutral} sizeClass={circle} />
      <Light active={probs.down === max} color="down" pct={probs.down} sizeClass={circle} />
      {showLabels && (
        <div className={cn("text-center text-gray-400 mt-1", text)}>
          <div className="text-green-400">{(probs.up * 100).toFixed(0)}%</div>
          <div className="text-yellow-400">{(probs.neutral * 100).toFixed(0)}%</div>
          <div className="text-red-400">{(probs.down * 100).toFixed(0)}%</div>
        </div>
      )}
    </div>
  );
}
