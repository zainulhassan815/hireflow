import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
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
  updateApplicationStatusMutation,
  type ApplicationResponse,
  type ApplicationStatus,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Typography } from "@/components/ui/typography";
import { cn } from "@/lib/utils";

/**
 * F44.b — the triage surface.
 *
 * One row per application. Each row:
 * - Name (links to `/documents/:source_document_id` if a resume exists)
 * - Match score 0-100 bar, cat-semantic color
 * - Current status badge (distinct visual from action affordance)
 * - Inline actions whose shape depends on status:
 *   - `new` → [Shortlist] + [Reject]
 *   - `shortlisted` / `rejected` → [Undo]
 *   - `interviewed` / `hired` → read-only badge, no actions
 *     (F93 Kanban owns those transitions; exposing them here would
 *     encourage accidental demotions from the "already decided" band)
 *
 * Optimistic mutation: click → row flips immediately via onMutate;
 * rolls back on error. HR triages quickly, the network shouldn't be
 * the bottleneck.
 *
 * Filter toolbar: free-text (name/email/skill), min-score slider,
 * status multi-select. Filtering is client-side; the full set ships
 * in one response so paginate later only if a job ever has >200
 * applications.
 */

type StatusFilter = "all" | ApplicationStatus;

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
        filteredCount={filtered.length}
      />

      <div className="overflow-hidden rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-xs tracking-wide uppercase">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Candidate</th>
              <th className="w-56 px-4 py-2 text-left font-medium">
                Match score
              </th>
              <th className="w-32 px-4 py-2 text-left font-medium">Status</th>
              <th className="w-56 px-4 py-2 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((app) => (
              <CandidateRow
                key={app.id}
                app={app}
                onStatusChanged={onStatusChanged}
              />
            ))}
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={4}
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

function CandidateRow({
  app,
  onStatusChanged,
}: {
  app: ApplicationResponse;
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

  return (
    <tr className="hover:bg-muted/30 border-b last:border-0">
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
