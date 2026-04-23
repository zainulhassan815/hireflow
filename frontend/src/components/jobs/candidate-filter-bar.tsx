/* eslint-disable react-refresh/only-export-components */
// ^ this module intentionally exports the shared filter hook +
// pure reducer alongside the filter-bar component. Splitting into
// two files would just add a second import line everywhere.

import {
  BookmarkIcon,
  FilterIcon,
  KeyboardIcon,
  SearchIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import type { ApplicationResponse, ApplicationStatus } from "@/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Typography } from "@/components/ui/typography";
import { cn } from "@/lib/utils";

/**
 * Filter state lives on the parent (detail page) so toggling between
 * list and Kanban preserves search / score tier / status multi-select
 * / saved views. Parent holds the state via `useCandidateFilters`,
 * passes setters + current values into `<CandidateFilterBar>`, and
 * uses `applyCandidateFilters` to reduce the raw applications to the
 * visible set each view receives.
 */

export type ScoreTier = "all" | "60" | "75" | "90";
export type StatusFilter = ApplicationStatus;

export interface SavedView {
  id: string;
  name: string;
  search: string;
  scoreTier: ScoreTier;
  statusSet: StatusFilter[];
}

// Saved views are job-agnostic recipes, keyed globally.
const SAVED_VIEWS_KEY = "hireflow.candidate-saved-views";

function loadSavedViews(): SavedView[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SAVED_VIEWS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as SavedView[];
  } catch {
    return [];
  }
}

function persistSavedViews(views: SavedView[]) {
  try {
    window.localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(views));
  } catch {
    // Safari private mode / quota exhausted — ignore silently.
  }
}

export const SCORE_TIERS: {
  value: ScoreTier;
  label: string;
  threshold: number;
}[] = [
  { value: "all", label: "All", threshold: 0 },
  { value: "60", label: "≥ 60%", threshold: 60 },
  { value: "75", label: "≥ 75%", threshold: 75 },
  { value: "90", label: "≥ 90%", threshold: 90 },
];

export const STATUS_LIST: {
  value: StatusFilter;
  label: string;
  dotClass: string;
}[] = [
  { value: "new", label: "New", dotClass: "bg-muted-foreground" },
  { value: "shortlisted", label: "Shortlisted", dotClass: "bg-success" },
  { value: "rejected", label: "Rejected", dotClass: "bg-destructive" },
  { value: "interviewed", label: "Interviewed", dotClass: "bg-cat-3" },
  { value: "hired", label: "Hired", dotClass: "bg-cat-1" },
];

export interface CandidateFiltersState {
  search: string;
  scoreTier: ScoreTier;
  statusSet: Set<StatusFilter>;
}

export interface CandidateFiltersApi {
  state: CandidateFiltersState;
  setSearch: (v: string) => void;
  setScoreTier: (v: ScoreTier) => void;
  setStatusSet: (v: Set<StatusFilter>) => void;
  savedViews: SavedView[];
  saveView: (name: string) => void;
  deleteView: (id: string) => void;
  applyView: (view: SavedView) => void;
  searchInputRef: React.RefObject<HTMLInputElement | null>;
  activeFilterCount: number;
}

/**
 * State-only hook — UI is deliberately separate so the filter bar
 * can be mounted in any layout.
 */
export function useCandidateFilters(): CandidateFiltersApi {
  const [search, setSearch] = React.useState("");
  const [scoreTier, setScoreTier] = React.useState<ScoreTier>("all");
  const [statusSet, setStatusSet] = React.useState<Set<StatusFilter>>(
    () => new Set()
  );
  const [savedViews, setSavedViews] = React.useState<SavedView[]>(() =>
    loadSavedViews()
  );
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  const applyView = React.useCallback((view: SavedView) => {
    setSearch(view.search);
    setScoreTier(view.scoreTier);
    setStatusSet(new Set(view.statusSet));
  }, []);

  const saveView = React.useCallback(
    (name: string) => {
      const view: SavedView = {
        id: crypto.randomUUID(),
        name,
        search,
        scoreTier,
        statusSet: Array.from(statusSet),
      };
      setSavedViews((prev) => {
        const next = [...prev, view];
        persistSavedViews(next);
        return next;
      });
      toast.success(`Saved view "${name}"`);
    },
    [search, scoreTier, statusSet]
  );

  const deleteView = React.useCallback((id: string) => {
    setSavedViews((prev) => {
      const next = prev.filter((v) => v.id !== id);
      persistSavedViews(next);
      return next;
    });
  }, []);

  const activeFilterCount =
    (scoreTier !== "all" ? 1 : 0) + (statusSet.size > 0 ? 1 : 0);

  return {
    state: { search, scoreTier, statusSet },
    setSearch,
    setScoreTier,
    setStatusSet,
    savedViews,
    saveView,
    deleteView,
    applyView,
    searchInputRef,
    activeFilterCount,
  };
}

/** Pure reducer: filter applications by current filter state. */
export function applyCandidateFilters(
  applications: ApplicationResponse[],
  state: CandidateFiltersState
): ApplicationResponse[] {
  const { search, scoreTier, statusSet } = state;
  const needle = search.trim().toLowerCase();
  const scoreThreshold =
    SCORE_TIERS.find((t) => t.value === scoreTier)?.threshold ?? 0;
  return applications.filter((app) => {
    if (statusSet.size > 0 && !statusSet.has(app.status)) return false;
    const score100 = Math.round((app.score ?? 0) * 100);
    if (score100 < scoreThreshold) return false;
    if (!needle) return true;
    const c = app.candidate;
    const haystacks = [c.name ?? "", c.email ?? "", ...(c.skills ?? [])].map(
      (s) => s.toLowerCase()
    );
    return haystacks.some((h) => h.includes(needle));
  });
}

export function CandidateFilterBar({
  api,
  totalCount,
  filteredCount,
  rightSlot,
}: {
  api: CandidateFiltersApi;
  totalCount: number;
  filteredCount: number;
  /** Optional right-side content — the view toggle slots in here. */
  rightSlot?: React.ReactNode;
}) {
  const {
    state: { search, scoreTier, statusSet },
    setSearch,
    setScoreTier,
    setStatusSet,
    savedViews,
    saveView,
    deleteView,
    applyView,
    searchInputRef,
    activeFilterCount,
  } = api;
  const activeTierMeta = SCORE_TIERS.find((t) => t.value === scoreTier);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            ref={searchInputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search — press / to focus"
            className="pl-9"
          />
        </div>

        <Popover>
          <PopoverTrigger
            render={
              <Button variant="outline">
                <FilterIcon className="size-4" data-icon="inline-start" />
                Filter
                {activeFilterCount > 0 && (
                  <span className="bg-primary text-primary-foreground ml-1 rounded-full px-1.5 text-[10px] leading-4 font-semibold">
                    {activeFilterCount}
                  </span>
                )}
              </Button>
            }
          />
          <PopoverContent align="end" className="w-80">
            <div className="flex flex-col gap-4">
              <div>
                <Typography
                  variant="small"
                  className="text-muted-foreground mb-2 block text-xs font-medium tracking-wide uppercase"
                >
                  Match score
                </Typography>
                <div className="grid grid-cols-4 gap-1">
                  {SCORE_TIERS.map((t) => (
                    <button
                      key={t.value}
                      type="button"
                      onClick={() => setScoreTier(t.value)}
                      className={cn(
                        "rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                        scoreTier === t.value
                          ? "bg-primary text-primary-foreground border-primary"
                          : "hover:bg-muted"
                      )}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <Typography
                  variant="small"
                  className="text-muted-foreground mb-2 block text-xs font-medium tracking-wide uppercase"
                >
                  Status
                </Typography>
                <div className="flex flex-col gap-1">
                  {STATUS_LIST.map((s) => {
                    const checked = statusSet.has(s.value);
                    return (
                      <label
                        key={s.value}
                        className="hover:bg-muted/50 flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            const next = new Set(statusSet);
                            if (v) next.add(s.value);
                            else next.delete(s.value);
                            setStatusSet(next);
                          }}
                        />
                        <span
                          aria-hidden
                          className={cn(
                            "inline-block size-2 rounded-full",
                            s.dotClass
                          )}
                        />
                        {s.label}
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
          </PopoverContent>
        </Popover>

        <SavedViewsButton
          views={savedViews}
          onApply={applyView}
          onSave={saveView}
          onDelete={deleteView}
          canSave={activeFilterCount > 0 || search.length > 0}
        />

        <span className="text-muted-foreground ml-auto text-xs tabular-nums">
          {filteredCount === totalCount
            ? `${totalCount} candidate${totalCount === 1 ? "" : "s"}`
            : `${filteredCount} of ${totalCount}`}
        </span>

        <KeyboardHint />

        {rightSlot}
      </div>

      {activeFilterCount > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {scoreTier !== "all" && activeTierMeta && (
            <FilterChip
              label={`Score ${activeTierMeta.label}`}
              onRemove={() => setScoreTier("all")}
            />
          )}
          {Array.from(statusSet).map((s) => {
            const meta = STATUS_LIST.find((m) => m.value === s);
            if (!meta) return null;
            return (
              <FilterChip
                key={s}
                label={meta.label}
                dotClass={meta.dotClass}
                onRemove={() => {
                  const next = new Set(statusSet);
                  next.delete(s);
                  setStatusSet(next);
                }}
              />
            );
          })}
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground ml-1 text-xs"
            onClick={() => {
              setScoreTier("all");
              setStatusSet(new Set());
            }}
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}

function FilterChip({
  label,
  dotClass,
  onRemove,
}: {
  label: string;
  dotClass?: string;
  onRemove: () => void;
}) {
  return (
    <span className="bg-muted text-foreground inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium">
      {dotClass && (
        <span
          aria-hidden
          className={cn("inline-block size-1.5 rounded-full", dotClass)}
        />
      )}
      {label}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${label} filter`}
        className="hover:bg-foreground/10 -mr-1 rounded-full p-0.5"
      >
        <XIcon className="size-3" />
      </button>
    </span>
  );
}

function SavedViewsButton({
  views,
  onApply,
  onSave,
  onDelete,
  canSave,
}: {
  views: SavedView[];
  onApply: (view: SavedView) => void;
  onSave: (name: string) => void;
  onDelete: (id: string) => void;
  canSave: boolean;
}) {
  const [name, setName] = React.useState("");
  const [open, setOpen] = React.useState(false);

  const trySave = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onSave(trimmed);
    setName("");
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant="outline" size="sm">
            <BookmarkIcon className="size-4" data-icon="inline-start" />
            Views
            {views.length > 0 && (
              <span className="bg-muted text-muted-foreground ml-1 rounded-full px-1.5 text-[10px] leading-4 font-semibold">
                {views.length}
              </span>
            )}
          </Button>
        }
      />
      <PopoverContent align="end" className="w-80">
        <div className="flex flex-col gap-3">
          <Typography
            variant="small"
            className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
          >
            Saved views
          </Typography>

          {views.length === 0 ? (
            <Typography
              variant="muted"
              className="bg-muted/40 rounded-md p-3 text-center text-xs"
            >
              No saved views yet. Set some filters and save the current view
              below.
            </Typography>
          ) : (
            <div className="flex flex-col gap-1">
              {views.map((view) => (
                <div
                  key={view.id}
                  className="hover:bg-muted/50 group flex items-center gap-2 rounded-md px-2 py-1.5"
                >
                  <button
                    type="button"
                    onClick={() => {
                      onApply(view);
                      setOpen(false);
                    }}
                    className="flex-1 truncate text-left text-sm"
                  >
                    {view.name}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(view.id)}
                    aria-label={`Delete ${view.name}`}
                    className="text-muted-foreground hover:text-destructive rounded p-1 opacity-0 transition-opacity group-hover:opacity-100"
                  >
                    <Trash2Icon className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="border-t pt-3">
            <Typography
              variant="muted"
              className="mb-1.5 block text-xs font-medium"
            >
              Save current view
            </Typography>
            <div className="flex gap-1">
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    trySave();
                  }
                }}
                placeholder={
                  canSave ? "e.g. High-score shortlist" : "Set filters first"
                }
                disabled={!canSave}
                className="h-8 text-xs"
              />
              <Button
                size="sm"
                onClick={trySave}
                disabled={!canSave || !name.trim()}
              >
                Save
              </Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function KeyboardHint() {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Keyboard shortcuts"
            title="Keyboard shortcuts"
          >
            <KeyboardIcon className="size-4" />
          </Button>
        }
      />
      <PopoverContent align="end" className="w-72">
        <div className="flex flex-col gap-2">
          <Typography
            variant="small"
            className="text-muted-foreground mb-1 block text-xs font-medium tracking-wide uppercase"
          >
            Keyboard shortcuts
          </Typography>
          <ShortcutRow label="Next / previous candidate (list)">
            <Kbd>j</Kbd>
            <Kbd>k</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Open drawer">
            <Kbd>Enter</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Close drawer / blur search">
            <Kbd>Esc</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Shortlist">
            <Kbd>s</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Reject">
            <Kbd>r</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Undo (back to new)">
            <Kbd>u</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Toggle selection (list)">
            <Kbd>x</Kbd>
          </ShortcutRow>
          <ShortcutRow label="Focus search">
            <Kbd>/</Kbd>
          </ShortcutRow>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ShortcutRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex gap-1">{children}</div>
    </div>
  );
}

/**
 * Empty-filter-results state. Rendered by each view when its
 * post-filter list is empty but the unfiltered count is non-zero.
 */
export function EmptyFiltersState({ api }: { api: CandidateFiltersApi }) {
  const { state, setSearch, setScoreTier, setStatusSet, activeFilterCount } =
    api;
  const hasSearch = state.search.length > 0;
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-md border border-dashed py-12 text-center">
      <span>No candidates match your filters.</span>
      {(activeFilterCount > 0 || hasSearch) && (
        <button
          type="button"
          onClick={() => {
            setSearch("");
            setScoreTier("all");
            setStatusSet(new Set());
          }}
          className="text-primary text-xs font-medium hover:underline"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
