import { useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronRightIcon,
  FilterIcon,
  KeyboardIcon,
  SearchIcon,
  UndoIcon,
  XIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  listJobApplicationsQueryKey,
  updateApplicationStatus,
  updateApplicationStatusMutation,
  type ApplicationResponse,
  type ApplicationStatus,
} from "@/api";
import { CandidateDrawer } from "@/components/jobs/candidate-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Typography } from "@/components/ui/typography";
import { cn, skillHueClass } from "@/lib/utils";

/**
 * F44.b/c/d — candidate triage surface.
 *
 * F44.d reworked the visual density against established ATS / issue-
 * tracker patterns (Linear issues, Lever pipeline, Notion database):
 * one quiet filter row, compact rows, always-visible action buttons,
 * active-filter chips, score-tier buttons instead of a range slider.
 *
 * Row actions (status change) use optimistic mutation: click → row
 * flips immediately via onMutate; rolls back on error.
 *
 * Sortable columns: click Candidate / Score header to toggle.
 *
 * Bulk select: checkbox column feeds a sticky toolbar. No bulk
 * backend endpoint today — frontend fans out N PATCHes with
 * optimistic cache patch; rolls the whole batch back on any failure.
 */

type StatusFilter = ApplicationStatus;
type ScoreTier = "all" | "60" | "75" | "90";
type SortKey = "score" | "name";
type SortDir = "asc" | "desc";

const SCORE_TIERS: { value: ScoreTier; label: string; threshold: number }[] = [
  { value: "all", label: "All", threshold: 0 },
  { value: "60", label: "≥ 60%", threshold: 60 },
  { value: "75", label: "≥ 75%", threshold: 75 },
  { value: "90", label: "≥ 90%", threshold: 90 },
];

const STATUS_LIST: {
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

interface JobCandidateListProps {
  applications: ApplicationResponse[];
  onStatusChanged: () => void;
}

export function JobCandidateList({
  applications,
  onStatusChanged,
}: JobCandidateListProps) {
  const [search, setSearch] = React.useState("");
  const [scoreTier, setScoreTier] = React.useState<ScoreTier>("all");
  const [statusSet, setStatusSet] = React.useState<Set<StatusFilter>>(
    () => new Set()
  );
  const [sortKey, setSortKey] = React.useState<SortKey>("score");
  const [sortDir, setSortDir] = React.useState<SortDir>("desc");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(
    () => new Set()
  );
  // F44.d.4 — drawer state lives here so F44.d.5's keyboard nav can
  // advance to the next/previous candidate without losing the drawer.
  const [drawerAppId, setDrawerAppId] = React.useState<string | null>(null);
  // F44.d.5 — which row has keyboard focus (visual ring), not DOM focus.
  const [focusedId, setFocusedId] = React.useState<string | null>(null);
  const searchInputRef = React.useRef<HTMLInputElement>(null);
  const rowRefs = React.useRef(new Map<string, HTMLTableRowElement>());

  const scoreThreshold =
    SCORE_TIERS.find((t) => t.value === scoreTier)?.threshold ?? 0;

  const filtered = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
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
  }, [applications, search, scoreThreshold, statusSet]);

  const sorted = React.useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortKey === "name") {
        const an = (a.candidate.name ?? a.candidate.email ?? "").toLowerCase();
        const bn = (b.candidate.name ?? b.candidate.email ?? "").toLowerCase();
        return an.localeCompare(bn) * dir;
      }
      const as = a.score ?? -Infinity;
      const bs = b.score ?? -Infinity;
      return (as - bs) * dir;
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  React.useEffect(() => {
    setSelectedIds((prev) => {
      const visible = new Set(sorted.map((a) => a.id));
      let changed = false;
      const next = new Set<string>();
      prev.forEach((id) => {
        if (visible.has(id)) next.add(id);
        else changed = true;
      });
      return changed ? next : prev;
    });
  }, [sorted]);

  const allVisibleSelected =
    sorted.length > 0 && sorted.every((a) => selectedIds.has(a.id));
  const someVisibleSelected =
    !allVisibleSelected && sorted.some((a) => selectedIds.has(a.id));

  const toggleAllVisible = () => {
    setSelectedIds((prev) => {
      if (allVisibleSelected) return new Set();
      const next = new Set(prev);
      sorted.forEach((a) => next.add(a.id));
      return next;
    });
  };

  const toggleRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const clearSelection = () => setSelectedIds(new Set());

  const selectedApps = React.useMemo(
    () => applications.filter((a) => selectedIds.has(a.id)),
    [applications, selectedIds]
  );

  const requestSort = (key: SortKey) => {
    // Don't nest setSortDir inside a setSortKey updater — React calls
    // updater fns twice in StrictMode and the toggle cancels itself,
    // which is exactly the "clicking the same column does nothing" bug
    // this replaces. Compute against the closure-captured current
    // state; React batches both setStates from the same event.
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  };

  const activeFilterCount =
    (scoreTier !== "all" ? 1 : 0) + (statusSet.size > 0 ? 1 : 0);
  const activeTierMeta = SCORE_TIERS.find((t) => t.value === scoreTier);

  // F44.d.5 — keyboard navigation. Resolves against the current
  // sorted+filtered list so j/k follows what the user sees.
  const focusedIndex = React.useMemo(
    () => (focusedId ? sorted.findIndex((a) => a.id === focusedId) : -1),
    [focusedId, sorted]
  );

  const moveFocus = React.useCallback(
    (delta: number) => {
      if (sorted.length === 0) return null;
      const current = focusedIndex >= 0 ? focusedIndex : -1;
      const next = Math.max(0, Math.min(sorted.length - 1, current + delta));
      const app = sorted[next];
      setFocusedId(app.id);
      // Scroll the focused row into view so long lists don't drop
      // focus off-screen.
      const el = rowRefs.current.get(app.id);
      if (el) el.scrollIntoView({ block: "nearest" });
      return app;
    },
    [focusedIndex, sorted]
  );

  const openDrawer = React.useCallback((app: ApplicationResponse) => {
    setDrawerAppId(app.id);
    setFocusedId(app.id);
  }, []);

  const drawerApp = React.useMemo(
    () =>
      drawerAppId
        ? (applications.find((a) => a.id === drawerAppId) ?? null)
        : null,
    [applications, drawerAppId]
  );

  // Single status mutation used by the row and by keyboard shortcuts
  // targeting the currently-focused row. Optimistic update mirrors
  // the per-row mutation.
  const queryKey =
    applications.length > 0
      ? listJobApplicationsQueryKey({
          path: { job_id: applications[0].job_id },
        })
      : null;

  const queryClient = useQueryClient();
  const shortcutMut = useMutation({
    ...updateApplicationStatusMutation(),
    onMutate: async (variables) => {
      if (!queryKey) return { previous: undefined };
      await queryClient.cancelQueries({ queryKey });
      const previous =
        queryClient.getQueryData<ApplicationResponse[]>(queryKey);
      const appId = variables.path?.application_id as string;
      const nextStatus = variables.body?.status as ApplicationStatus;
      queryClient.setQueryData<ApplicationResponse[]>(queryKey, (old) =>
        (old ?? []).map((a) =>
          a.id === appId ? { ...a, status: nextStatus } : a
        )
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (queryKey && ctx?.previous)
        queryClient.setQueryData(queryKey, ctx.previous);
      toast.error("Status change failed; rolled back.");
    },
    onSuccess: () => onStatusChanged(),
  });

  const setStatusFor = React.useCallback(
    (appId: string, status: ApplicationStatus) => {
      shortcutMut.mutate({
        path: { application_id: appId },
        body: { status },
      });
    },
    [shortcutMut]
  );

  // Global keyboard listener, scoped to the list's lifetime. Ignores
  // keys when an input/textarea is focused, when a modifier is held,
  // or when a dialog is modal over the page. The drawer itself is
  // Sheet-backed and also handles its own j/k via `drawerKeyDown`.
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      const isTyping =
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        (e.target as HTMLElement | null)?.isContentEditable;
      // When the drawer is open, only j/k/s/r/u/Escape are meaningful;
      // other shortcuts fall through to Sheet's own handlers.
      const drawerOpen = drawerAppId != null;
      if (isTyping) {
        if (e.key === "Escape" && searchInputRef.current === e.target) {
          setSearch("");
          searchInputRef.current?.blur();
        }
        return;
      }
      const key = e.key;
      if (key === "j" || key === "ArrowDown") {
        e.preventDefault();
        const next = moveFocus(1);
        if (drawerOpen && next) setDrawerAppId(next.id);
      } else if (key === "k" || key === "ArrowUp") {
        e.preventDefault();
        const next = moveFocus(-1);
        if (drawerOpen && next) setDrawerAppId(next.id);
      } else if (key === "Enter") {
        if (drawerOpen) return;
        const app = focusedId
          ? sorted.find((a) => a.id === focusedId)
          : sorted[0];
        if (app) {
          e.preventDefault();
          openDrawer(app);
        }
      } else if (key === "Escape" && drawerOpen) {
        // Sheet handles Escape too; belt-and-braces.
        setDrawerAppId(null);
      } else if (key === "s" || key === "r" || key === "u") {
        const target = drawerOpen
          ? drawerAppId
          : focusedId || sorted[0]?.id || null;
        if (!target) return;
        const app = applications.find((a) => a.id === target);
        if (!app) return;
        if (app.status === "interviewed" || app.status === "hired") return;
        const next: ApplicationStatus =
          key === "s" ? "shortlisted" : key === "r" ? "rejected" : "new";
        e.preventDefault();
        setStatusFor(app.id, next);
      } else if (key === "x" && !drawerOpen) {
        const id = focusedId || sorted[0]?.id;
        if (!id) return;
        e.preventDefault();
        setSelectedIds((prev) => {
          const nextSet = new Set(prev);
          if (nextSet.has(id)) nextSet.delete(id);
          else nextSet.add(id);
          return nextSet;
        });
      } else if (key === "/" && !drawerOpen) {
        e.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    applications,
    drawerAppId,
    focusedId,
    moveFocus,
    openDrawer,
    setStatusFor,
    sorted,
  ]);

  return (
    <div className="flex flex-col gap-3">
      <FilterRow
        search={search}
        onSearch={setSearch}
        searchInputRef={searchInputRef}
        scoreTier={scoreTier}
        onScoreTier={setScoreTier}
        statusSet={statusSet}
        onStatusSet={setStatusSet}
        activeFilterCount={activeFilterCount}
        totalCount={applications.length}
        filteredCount={sorted.length}
      />

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
                  setStatusSet((prev) => {
                    const next = new Set(prev);
                    next.delete(s);
                    return next;
                  });
                }}
              />
            );
          })}
          {activeFilterCount > 0 && (
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
          )}
        </div>
      )}

      {selectedIds.size > 0 && (
        <BulkActionBar
          selected={selectedApps}
          onApplied={() => {
            clearSelection();
            onStatusChanged();
          }}
          onCancel={clearSelection}
        />
      )}

      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/20 text-muted-foreground">
            <tr>
              <th className="w-10 px-3 py-2.5">
                <Checkbox
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  onCheckedChange={toggleAllVisible}
                  aria-label="Select all visible candidates"
                />
              </th>
              <SortableHeader
                label="Candidate"
                active={sortKey === "name"}
                dir={sortDir}
                onClick={() => requestSort("name")}
              />
              <SortableHeader
                label="Match"
                active={sortKey === "score"}
                dir={sortDir}
                onClick={() => requestSort("score")}
                className="w-40"
              />
              <th className="w-32 px-4 py-2.5 text-left text-xs font-medium">
                Status
              </th>
              <th className="w-48 px-4 py-2.5 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((app) => (
              <CandidateRow
                key={app.id}
                app={app}
                selected={selectedIds.has(app.id)}
                focused={focusedId === app.id}
                onToggleSelect={() => toggleRow(app.id)}
                onStatusChanged={onStatusChanged}
                onOpen={() => openDrawer(app)}
                onHover={() => setFocusedId(app.id)}
                registerRef={(el) => {
                  if (el) rowRefs.current.set(app.id, el);
                  else rowRefs.current.delete(app.id);
                }}
              />
            ))}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="text-muted-foreground px-4 py-12 text-center"
                >
                  <div className="flex flex-col items-center gap-2">
                    <span>No candidates match your filters.</span>
                    {activeFilterCount > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setScoreTier("all");
                          setStatusSet(new Set());
                        }}
                        className="text-primary text-xs font-medium hover:underline"
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <CandidateDrawer
        app={drawerApp}
        onOpenChange={(open) => {
          if (!open) setDrawerAppId(null);
        }}
        onStatusChanged={onStatusChanged}
      />
    </div>
  );
}

/* -------------------------------- Filter row ------------------------------ */

function FilterRow({
  search,
  onSearch,
  searchInputRef,
  scoreTier,
  onScoreTier,
  statusSet,
  onStatusSet,
  activeFilterCount,
  totalCount,
  filteredCount,
}: {
  search: string;
  onSearch: (v: string) => void;
  searchInputRef: React.RefObject<HTMLInputElement | null>;
  scoreTier: ScoreTier;
  onScoreTier: (v: ScoreTier) => void;
  statusSet: Set<StatusFilter>;
  onStatusSet: (v: Set<StatusFilter>) => void;
  activeFilterCount: number;
  totalCount: number;
  filteredCount: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[220px] flex-1">
        <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          ref={searchInputRef}
          value={search}
          onChange={(e) => onSearch(e.target.value)}
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
                    onClick={() => onScoreTier(t.value)}
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
                          onStatusSet(next);
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

      <span className="text-muted-foreground ml-auto text-xs tabular-nums">
        {filteredCount === totalCount
          ? `${totalCount} candidate${totalCount === 1 ? "" : "s"}`
          : `${filteredCount} of ${totalCount}`}
      </span>

      <KeyboardHint />
    </div>
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
          <ShortcutRow label="Next / previous candidate">
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
          <ShortcutRow label="Toggle selection">
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

/* -------------------------------- Bulk bar -------------------------------- */

function BulkActionBar({
  selected,
  onApplied,
  onCancel,
}: {
  selected: ApplicationResponse[];
  onApplied: () => void;
  onCancel: () => void;
}) {
  const [pending, setPending] = React.useState(false);
  const queryClient = useQueryClient();

  const actionable = selected.filter(
    (a) =>
      a.status === "new" ||
      a.status === "shortlisted" ||
      a.status === "rejected"
  );

  const applyBulk = async (status: ApplicationStatus) => {
    if (actionable.length === 0) return;
    setPending(true);
    const jobId = actionable[0].job_id;
    const queryKey = listJobApplicationsQueryKey({ path: { job_id: jobId } });
    await queryClient.cancelQueries({ queryKey });
    const previous = queryClient.getQueryData<ApplicationResponse[]>(queryKey);
    const targetIds = new Set(actionable.map((a) => a.id));
    queryClient.setQueryData<ApplicationResponse[]>(queryKey, (old) =>
      (old ?? []).map((a) => (targetIds.has(a.id) ? { ...a, status } : a))
    );

    const results = await Promise.allSettled(
      actionable.map((a) =>
        updateApplicationStatus({
          path: { application_id: a.id },
          body: { status },
        })
      )
    );
    const failed = results.filter((r) => r.status === "rejected").length;
    setPending(false);
    if (failed > 0) {
      if (previous) queryClient.setQueryData(queryKey, previous);
      toast.error(
        failed === actionable.length
          ? "Bulk change failed; rolled back."
          : `${failed} of ${actionable.length} changes failed; rolled back.`
      );
      return;
    }
    toast.success(
      `${actionable.length} candidate${actionable.length === 1 ? "" : "s"} ${
        status === "shortlisted" ? "shortlisted" : "rejected"
      }.`
    );
    onApplied();
  };

  const skipped = selected.length - actionable.length;

  return (
    <div className="bg-primary text-primary-foreground sticky top-2 z-10 flex flex-wrap items-center gap-3 rounded-lg px-4 py-2 text-sm shadow">
      <span className="font-medium">
        {selected.length} selected
        {skipped > 0 && (
          <span className="text-primary-foreground/70 ml-1 text-xs">
            ({skipped} already interviewed/hired — skipped)
          </span>
        )}
      </span>
      <div className="ml-auto flex gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => applyBulk("shortlisted")}
          disabled={pending || actionable.length === 0}
        >
          <CheckIcon className="size-4" data-icon="inline-start" />
          Shortlist {actionable.length}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => applyBulk("rejected")}
          disabled={pending || actionable.length === 0}
          className="text-destructive"
        >
          <XIcon className="size-4" data-icon="inline-start" />
          Reject {actionable.length}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={onCancel}
          disabled={pending}
          className="text-primary-foreground hover:bg-primary-foreground/10"
        >
          Clear
        </Button>
      </div>
    </div>
  );
}

/* --------------------------------- Rows ----------------------------------- */

function SortableHeader({
  label,
  active,
  dir,
  onClick,
  className,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  className?: string;
}) {
  return (
    <th className={cn("px-4 py-2.5 text-left text-xs font-medium", className)}>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 rounded transition-colors",
          active ? "text-foreground" : "hover:text-foreground"
        )}
      >
        {label}
        {active &&
          (dir === "asc" ? (
            <ArrowUpIcon className="size-3" />
          ) : (
            <ArrowDownIcon className="size-3" />
          ))}
      </button>
    </th>
  );
}

function CandidateRow({
  app,
  selected,
  focused,
  onToggleSelect,
  onStatusChanged,
  onOpen,
  onHover,
  registerRef,
}: {
  app: ApplicationResponse;
  selected: boolean;
  focused: boolean;
  onToggleSelect: () => void;
  onStatusChanged: () => void;
  onOpen: () => void;
  onHover: () => void;
  registerRef: (el: HTMLTableRowElement | null) => void;
}) {
  const queryClient = useQueryClient();
  const queryKey = listJobApplicationsQueryKey({
    path: { job_id: app.job_id },
  });

  const mut = useMutation({
    ...updateApplicationStatusMutation(),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey });
      const previous =
        queryClient.getQueryData<ApplicationResponse[]>(queryKey);
      const nextStatus = variables.body?.status as ApplicationStatus;
      queryClient.setQueryData<ApplicationResponse[]>(queryKey, (old) =>
        (old ?? []).map((a) =>
          a.id === app.id ? { ...a, status: nextStatus } : a
        )
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) {
        queryClient.setQueryData(queryKey, ctx.previous);
      }
      toast.error("Status change failed; rolled back.");
    },
    onSuccess: () => {
      onStatusChanged();
    },
  });

  const setStatus = (status: ApplicationStatus) => {
    mut.mutate({ path: { application_id: app.id }, body: { status } });
  };

  const c = app.candidate;
  const displayName = c.name || c.email || "Unnamed candidate";
  const score100 = Math.round((app.score ?? 0) * 100);
  const updated = new Date(app.updated_at);

  // Row-level click opens the drawer — a pointer-only convenience,
  // not a semantic claim. The keyboard-accessible trigger is the
  // name button inside the Candidate cell. Interactive children
  // (checkbox, name button, action buttons) stopPropagation so they
  // don't bubble back into this handler.
  const openDrawerFromRowClick = (e: React.MouseEvent) => {
    if (e.defaultPrevented) return;
    onOpen();
  };

  return (
    <tr
      ref={registerRef}
      className={cn(
        "group relative cursor-pointer border-b transition-colors last:border-0",
        // Three states with distinct visuals so hover, keyboard-focus,
        // and selection never feel alike:
        //   selected  → primary-tinted bg + 3px left strip
        //   focused   → muted bg + full inset primary ring
        //   hover     → just the muted bg
        selected && "bg-primary/10",
        focused &&
          !selected &&
          "bg-muted shadow-[inset_0_0_0_2px_var(--color-primary)]",
        !selected && !focused && "hover:bg-muted/40"
      )}
      onClick={openDrawerFromRowClick}
      onMouseEnter={onHover}
    >
      <td
        className="relative px-3 py-3 align-middle"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Selection left-strip. (Focused state uses the inset box
            shadow above so it doesn't compete with the strip.) */}
        {selected && (
          <span
            aria-hidden
            className="bg-primary absolute top-0 bottom-0 left-0 w-[3px]"
          />
        )}
        <Checkbox
          checked={selected}
          onCheckedChange={onToggleSelect}
          aria-label={`Select ${displayName}`}
        />
      </td>
      <td className="px-4 py-3 align-middle">
        <div className="flex items-start gap-3">
          <Avatar name={c.name} email={c.email} />
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger
                  render={
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpen();
                      }}
                      className="focus-visible:ring-ring/50 inline-flex items-center gap-1 rounded text-left font-medium hover:underline focus-visible:ring-2 focus-visible:outline-none"
                    >
                      {displayName}
                      <ChevronRightIcon className="size-3 opacity-40" />
                    </button>
                  }
                />
                <TooltipContent>
                  Updated {formatDistanceToNow(updated, { addSuffix: true })}
                </TooltipContent>
              </Tooltip>
              {c.email && (
                <span className="text-muted-foreground truncate text-xs">
                  {c.email}
                </span>
              )}
            </div>
            {c.skills && c.skills.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {c.skills.slice(0, 3).map((skill) => (
                  <Badge
                    key={skill}
                    variant="outline"
                    className={cn(
                      "h-5 px-1.5 text-[11px] font-normal",
                      skillHueClass(skill)
                    )}
                  >
                    {skill}
                  </Badge>
                ))}
                {c.skills.length > 3 && (
                  <Badge
                    variant="outline"
                    className="h-5 px-1.5 text-[11px] font-normal"
                  >
                    +{c.skills.length - 3}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>
      </td>
      <td className="px-4 py-3 align-middle">
        <MatchScoreBar score={score100} />
      </td>
      <td className="px-4 py-3 align-middle">
        <StatusLabel status={app.status} />
      </td>
      <td
        className="px-4 py-3 text-right align-middle"
        onClick={(e) => e.stopPropagation()}
      >
        <ActionButtons
          status={app.status}
          onSetStatus={setStatus}
          pending={mut.isPending}
        />
      </td>
    </tr>
  );
}

function MatchScoreBar({ score }: { score: number }) {
  const color =
    score >= 80
      ? "bg-success"
      : score >= 60
        ? "bg-warning"
        : "bg-muted-foreground";
  return (
    <div className="flex items-center gap-2">
      <div className="bg-muted h-1.5 w-24 overflow-hidden rounded-full">
        <div
          className={cn("h-full rounded-full transition-[width]", color)}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-muted-foreground w-8 shrink-0 text-xs tabular-nums">
        {score}%
      </span>
    </div>
  );
}

function StatusLabel({ status }: { status: ApplicationStatus }) {
  const meta: Record<
    ApplicationStatus,
    { label: string; dot: string; text: string }
  > = {
    new: {
      label: "New",
      dot: "bg-muted-foreground",
      text: "text-muted-foreground",
    },
    shortlisted: {
      label: "Shortlisted",
      dot: "bg-success",
      text: "text-success",
    },
    rejected: {
      label: "Rejected",
      dot: "bg-destructive",
      text: "text-destructive",
    },
    interviewed: {
      label: "Interviewed",
      dot: "bg-cat-3",
      text: "text-cat-3",
    },
    hired: {
      label: "Hired",
      dot: "bg-cat-1",
      text: "text-cat-1",
    },
  };
  const m = meta[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", m.text)}>
      <span
        aria-hidden
        className={cn("inline-block size-1.5 rounded-full", m.dot)}
      />
      {m.label}
    </span>
  );
}

function ActionButtons({
  status,
  onSetStatus,
  pending,
}: {
  status: ApplicationStatus;
  onSetStatus: (s: ApplicationStatus) => void;
  pending: boolean;
}) {
  if (status === "interviewed" || status === "hired") {
    return (
      <Typography variant="muted" className="text-xs italic">
        Managed on Kanban
      </Typography>
    );
  }

  if (status === "new") {
    return (
      <div className="flex justify-end gap-1">
        <Button
          size="sm"
          onClick={() => onSetStatus("shortlisted")}
          disabled={pending}
        >
          <CheckIcon className="size-4" data-icon="inline-start" />
          Shortlist
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onSetStatus("rejected")}
          disabled={pending}
          className="text-destructive"
        >
          <XIcon className="size-4" data-icon="inline-start" />
          Reject
        </Button>
      </div>
    );
  }

  return (
    <div className="flex justify-end">
      <Button
        size="sm"
        variant="ghost"
        onClick={() => onSetStatus("new")}
        disabled={pending}
      >
        <UndoIcon className="size-4" data-icon="inline-start" />
        Undo
      </Button>
    </div>
  );
}

function candidateInitials(
  name: string | null | undefined,
  email: string | null | undefined
): string {
  const source = (name ?? email ?? "?").trim();
  if (!source || source === "?") return "?";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}

function Avatar({
  name,
  email,
}: {
  name: string | null | undefined;
  email: string | null | undefined;
}) {
  // Pseudo-random hue per candidate — same `skillHueClass` hash used
  // elsewhere, so a given person keeps the same color across pages.
  // Driven by display name; falls back to email for anonymous resumes.
  const key = name || email || "?";
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
        skillHueClass(key)
      )}
    >
      {candidateInitials(name, email)}
    </span>
  );
}
