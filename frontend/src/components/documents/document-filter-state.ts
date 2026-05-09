/**
 * F32 — filter-state shape + helpers shared by the search +
 * documents pages.
 *
 * Lives in a dedicated file so the bar component
 * (``document-filter-bar.tsx``) can stay component-only — eslint's
 * ``react-refresh/only-export-components`` rule fires on
 * mixed-export files.
 */

import type { DocumentType } from "@/api/generated";

export interface FilterState {
  document_type: DocumentType | null;
  skills: string[];
  min_experience_years: number | null;
  date_from: string | null; // ISO "YYYY-MM-DD"
  date_to: string | null; // ISO "YYYY-MM-DD"
}

export const EMPTY_FILTERS: FilterState = {
  document_type: null,
  skills: [],
  min_experience_years: null,
  date_from: null,
  date_to: null,
};

export function isAnyFilterActive(state: FilterState): boolean {
  return (
    state.document_type !== null ||
    state.skills.length > 0 ||
    state.min_experience_years !== null ||
    state.date_from !== null ||
    state.date_to !== null
  );
}

/**
 * Convert UI ``FilterState`` (date strings) into the API shape
 * (datetime). End-of-day handling for ``date_to`` happens here so
 * the operator's "through May 9" reads as inclusive of the whole
 * day.
 */
export function toApiFilters(state: FilterState): {
  document_type?: DocumentType;
  skills?: string[];
  min_experience_years?: number;
  date_from?: string;
  date_to?: string;
} {
  const out: ReturnType<typeof toApiFilters> = {};
  if (state.document_type) out.document_type = state.document_type;
  if (state.skills.length > 0) out.skills = state.skills;
  if (state.min_experience_years !== null)
    out.min_experience_years = state.min_experience_years;
  if (state.date_from) out.date_from = `${state.date_from}T00:00:00Z`;
  if (state.date_to) out.date_to = `${state.date_to}T23:59:59Z`;
  return out;
}
