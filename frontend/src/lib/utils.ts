import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(date));
}

export function formatDateTime(date: Date | string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Deterministic hash → cat-hue class. Same input always resolves to
// the same hue across pages, so e.g. "Python" reads identically in
// the candidates table and on a job card. Case-insensitive so
// "python" and "Python" land on the same lane.
// Pastel chip treatment: /20 alpha bg (light tinted surface) paired
// with the matching cat-*-ink foreground (dark saturated text).
// Mirrors GitHub-label aesthetics while staying inside the design
// token system — see --cat-X-ink in index.css.
const SKILL_HUE_PALETTE = [
  "bg-cat-1/15 text-cat-1-ink border-transparent",
  "bg-cat-2/15 text-cat-2-ink border-transparent",
  "bg-cat-3/15 text-cat-3-ink border-transparent",
  "bg-cat-4/15 text-cat-4-ink border-transparent",
  "bg-cat-5/15 text-cat-5-ink border-transparent",
] as const;

export function skillHueClass(skill: string): string {
  const s = skill.toLowerCase();
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    hash = (hash * 31 + s.charCodeAt(i)) | 0;
  }
  return SKILL_HUE_PALETTE[Math.abs(hash) % SKILL_HUE_PALETTE.length];
}
