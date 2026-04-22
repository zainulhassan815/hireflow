import { useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronRightIcon,
  SearchIcon,
  UndoIcon,
  XIcon,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  listJobApplicationsQueryKey,
  updateApplicationStatus,
  updateApplicationStatusMutation,
  type ApplicationResponse,
  type ApplicationStatus,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Typography } from "@/components/ui/typography";
import { cn } from "@/lib/utils";

/**
 * F44.b/c — the triage surface.
 *
 * One row per application. Each row:
 * - Checkbox for bulk selection (F44.c).
 * - Name (links to `/documents/:source_document_id` if a resume exists).
 * - Match score 0-100 bar, cat-semantic color.
 * - Current status badge (distinct visual from action affordance).
 * - Inline actions whose shape depends on status:
 *   - `new` → [Shortlist] + [Reject]
 *   - `shortlisted` / `rejected` → [Undo]
 *   - `interviewed` / `hired` → read-only; F93 Kanban owns those.
 *
 * Optimistic mutation: click → row flips immediately via onMutate;
 * rolls back on error.
 *
 * Filter toolbar (F44.b): free-text (name/email/skill), min-score
 * slider, status pills. Client-side — full set ships in one response.
 *
 * Sortable columns (F44.c): click a header to sort by Score / Name /
 * Updated. Score descending is the default (triage rank order).
 *
 * Bulk actions (F44.c): selecting rows surfaces a sticky toolbar with
 * [Shortlist all] / [Reject all]. Backend has no bulk endpoint today
 * so the frontend fans out N PATCHes with optimistic updates; acceptable
 * for N ≤ 50 (the list size cap) and avoids a server-side API addition.
 */

type StatusFilter = "all" | ApplicationStatus;
type SortKey = "score" | "name" | "updated";
type SortDir = "asc" | "desc";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "new", label: "New" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "rejected", label: "Rejected" },
  { value: "interviewed", label: "Interviewed" },
  { value: "hired", label: "Hired" },
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
  const [minScore, setMinScore] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");
  const [sortKey, setSortKey] = React.useState<SortKey>("score");
  const [sortDir, setSortDir] = React.useState<SortDir>("desc");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(
    () => new Set()
  );

  const filtered = React.useMemo(() => {
    const needle = search.trim().toLowerCase();
    return applications.filter((app) => {
      if (statusFilter !== "all" && app.status !== statusFilter) return false;
      const score100 = Math.round((app.score ?? 0) * 100);
      if (score100 < minScore) return false;
      if (!needle) return true;
      const c = app.candidate;
      const haystacks = [c.name ?? "", c.email ?? "", ...(c.skills ?? [])].map(
        (s) => s.toLowerCase()
      );
      return haystacks.some((h) => h.includes(needle));
    });
  }, [applications, search, minScore, statusFilter]);

  const sorted = React.useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortKey === "name") {
        const an = (a.candidate.name ?? a.candidate.email ?? "").toLowerCase();
        const bn = (b.candidate.name ?? b.candidate.email ?? "").toLowerCase();
        return an.localeCompare(bn) * dir;
      }
      if (sortKey === "updated") {
        return (
          (new Date(a.updated_at).getTime() -
            new Date(b.updated_at).getTime()) *
          dir
        );
      }
      // score — nulls fall to the bottom regardless of direction, which
      // matches "haven't been scored" being least actionable in both
      // directions.
      const as = a.score ?? -Infinity;
      const bs = b.score ?? -Infinity;
      return (as - bs) * dir;
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  // Keep selection coherent with the current filtered view — if the
  // filter excludes a selected row, it's no longer actionable from the
  // bulk toolbar, so drop it.
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
    setSortKey((prevKey) => {
      if (prevKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return prevKey;
      }
      // Score defaults to desc (top matches first); name asc; updated desc.
      setSortDir(key === "name" ? "asc" : "desc");
      return key;
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <Toolbar
        search={search}
        onSearch={setSearch}
        minScore={minScore}
        onMinScoreChange={setMinScore}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        totalCount={applications.length}
        filteredCount={sorted.length}
      />

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
          <thead className="bg-muted/50 text-muted-foreground text-xs tracking-wide uppercase">
            <tr>
              <th className="w-10 px-3 py-2">
                <Checkbox
                  checked={
                    allVisibleSelected
                      ? true
                      : someVisibleSelected
                        ? "indeterminate"
                        : false
                  }
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
                label="Match score"
                active={sortKey === "score"}
                dir={sortDir}
                onClick={() => requestSort("score")}
                className="w-56"
              />
              <SortableHeader
                label="Updated"
                active={sortKey === "updated"}
                dir={sortDir}
                onClick={() => requestSort("updated")}
                className="w-32"
              />
              <th className="w-32 px-4 py-2 text-left font-medium">Status</th>
              <th className="w-56 px-4 py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((app) => (
              <CandidateRow
                key={app.id}
                app={app}
                selected={selectedIds.has(app.id)}
                onToggleSelect={() => toggleRow(app.id)}
                onStatusChanged={onStatusChanged}
              />
            ))}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="text-muted-foreground px-4 py-8 text-center"
                >
                  No candidates match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

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
    <th className={cn("px-4 py-2 text-left font-medium", className)}>
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

function Toolbar({
  search,
  onSearch,
  minScore,
  onMinScoreChange,
  statusFilter,
  onStatusFilter,
  totalCount,
  filteredCount,
}: {
  search: string;
  onSearch: (v: string) => void;
  minScore: number;
  onMinScoreChange: (v: number) => void;
  statusFilter: StatusFilter;
  onStatusFilter: (v: StatusFilter) => void;
  totalCount: number;
  filteredCount: number;
}) {
  return (
    <div className="bg-card flex flex-wrap items-center gap-2 rounded-lg border p-3">
      <div className="relative min-w-[200px] flex-1">
        <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search name, email, or skill"
          className="pl-9"
        />
      </div>

      <div className="flex items-center gap-2">
        <Typography variant="muted" className="shrink-0 text-xs">
          Min score
        </Typography>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={minScore}
          onChange={(e) => onMinScoreChange(Number(e.target.value))}
          className="accent-primary h-1 w-32 cursor-pointer"
          aria-label="Minimum match score"
        />
        <span className="text-muted-foreground w-10 text-sm tabular-nums">
          {minScore}%
        </span>
      </div>

      <div className="flex items-center gap-1">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onStatusFilter(opt.value)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              statusFilter === opt.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="text-muted-foreground ml-auto text-xs">
        {filteredCount === totalCount
          ? `${totalCount} candidate${totalCount === 1 ? "" : "s"}`
          : `${filteredCount} of ${totalCount}`}
      </div>
    </div>
  );
}

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

  // "Actionable" triagable rows — already-decided status rows are
  // skipped silently (F93 owns interviewed/hired transitions). The
  // counter reflects how many will actually change.
  const actionable = selected.filter(
    (a) =>
      a.status === "new" ||
      a.status === "shortlisted" ||
      a.status === "rejected"
  );

  const applyBulk = async (status: ApplicationStatus) => {
    if (actionable.length === 0) return;
    setPending(true);

    // Fan-out N PATCHes. Backend has no bulk endpoint today; list
    // ceilings at 50 so worst case is 50 parallel requests. Each one
    // uses the real mutation so all server-side invariants hold.
    // Optimistic update patches the cache immediately so the UI
    // doesn't flicker.
    const jobId = actionable[0].job_id;
    const queryKey = listJobApplicationsQueryKey({
      path: { job_id: jobId },
    });
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
      // Roll back on ANY failure — partial success is worse UX than
      // "redo the whole selection" because HR can't tell which rows
      // succeeded without scanning the table. For F44.c scope that
      // trade is right; revisit if bulk sizes grow.
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

function CandidateRow({
  app,
  selected,
  onToggleSelect,
  onStatusChanged,
}: {
  app: ApplicationResponse;
  selected: boolean;
  onToggleSelect: () => void;
  onStatusChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const queryKey = listJobApplicationsQueryKey({
    path: { job_id: app.job_id },
  });

  const mut = useMutation({
    ...updateApplicationStatusMutation(),
    // F44.b — optimistic update. HR clicks should feel instant.
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
    mut.mutate({
      path: { application_id: app.id },
      body: { status },
    });
  };

  const c = app.candidate;
  const displayName = c.name || c.email || "Unnamed candidate";
  const score100 = Math.round((app.score ?? 0) * 100);
  const updated = new Date(app.updated_at);

  return (
    <tr
      className={cn(
        "border-b last:border-0",
        selected ? "bg-primary/5" : "hover:bg-muted/30"
      )}
    >
      <td className="px-3 py-3">
        <Checkbox
          checked={selected}
          onCheckedChange={onToggleSelect}
          aria-label={`Select ${displayName}`}
        />
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col">
          {c.source_document_id ? (
            <Link
              to={`/documents/${c.source_document_id}`}
              className="inline-flex items-center gap-1 font-medium hover:underline"
            >
              {displayName}
              <ChevronRightIcon className="size-3 opacity-50" />
            </Link>
          ) : (
            <span className="font-medium">{displayName}</span>
          )}
          {c.email && (
            <span className="text-muted-foreground text-xs">{c.email}</span>
          )}
          {c.skills && c.skills.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {c.skills.slice(0, 4).map((skill) => (
                <Badge key={skill} variant="outline" className="text-xs">
                  {skill}
                </Badge>
              ))}
              {c.skills.length > 4 && (
                <Badge variant="outline" className="text-xs">
                  +{c.skills.length - 4}
                </Badge>
              )}
            </div>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <MatchScoreBar score={score100} />
      </td>
      <td className="text-muted-foreground px-4 py-3 text-xs">
        {formatDistanceToNow(updated, { addSuffix: true })}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={app.status} />
      </td>
      <td className="px-4 py-3 text-right">
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
      <div className="bg-muted h-2 flex-1 overflow-hidden rounded">
        <div
          className={cn("h-full rounded transition-[width]", color)}
          style={{ width: `${Math.max(score, 2)}%` }}
        />
      </div>
      <span className="text-muted-foreground w-10 shrink-0 text-xs tabular-nums">
        {score}%
      </span>
    </div>
  );
}

function StatusBadge({ status }: { status: ApplicationStatus }) {
  const styles: Record<ApplicationStatus, string> = {
    new: "bg-muted text-muted-foreground",
    shortlisted: "bg-success text-success-foreground",
    rejected: "bg-destructive/15 text-destructive",
    interviewed: "bg-cat-3/15 text-cat-3",
    hired: "bg-cat-1/15 text-cat-1",
  };
  const labels: Record<ApplicationStatus, string> = {
    new: "New",
    shortlisted: "✓ Shortlisted",
    rejected: "✗ Rejected",
    interviewed: "Interviewed",
    hired: "Hired",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        styles[status]
      )}
    >
      {labels[status]}
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
    // F93 Kanban owns these transitions; no inline affordance here.
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

  // shortlisted or rejected → Undo returns to `new`.
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() => onSetStatus("new")}
      disabled={pending}
    >
      <UndoIcon className="size-4" data-icon="inline-start" />
      Undo
    </Button>
  );
}

