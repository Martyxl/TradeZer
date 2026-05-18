import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTime(iso: string): string {
  // Backend ukládá časy jako UTC bez timezone suffixu — explicitně přidáme Z
  const normalized = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  return new Date(normalized).toLocaleString("cs-CZ", {
    timeZone: "Europe/Prague",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  const normalized = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  return new Date(normalized).toLocaleDateString("cs-CZ", {
    timeZone: "Europe/Prague",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatPercent(val: number): string {
  return `${(val * 100).toFixed(1)}%`;
}

export type Direction = "down" | "neutral" | "up";

export function dominantDirection(
  probDown: number,
  probNeutral: number,
  probUp: number
): Direction {
  if (probUp >= probDown && probUp >= probNeutral) return "up";
  if (probDown >= probNeutral) return "down";
  return "neutral";
}

export function importanceBadge(weight: number | null): "S" | "M" | "L" {
  if (!weight) return "S";
  if (weight >= 0.6) return "L";
  if (weight >= 0.3) return "M";
  return "S";
}
