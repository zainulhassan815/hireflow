import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  BriefcaseIcon,
  ChevronDownIcon,
  LayoutGridIcon,
  ListIcon,
  Loader2Icon,
  MoreHorizontalIcon,
  PencilIcon,
  SparklesIcon,
  TrashIcon,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import {
  changeJobStatusMutation,
  deleteJob,
  getJobOptions,
  getJobQueryKey,
  listJobApplicationsOptions,
  listJobApplicationsQueryKey,
  matchCandidatesMutation,
  type ApplicationResponse,
  type ErrorResponse,
  type JobResponse,
  type JobStatus,
} from "@/api";
import {
  CandidateFilterBar,
  EmptyFiltersState,
  applyCandidateFilters,
  useCandidateFilters,
} from "@/components/jobs/candidate-filter-bar";
import { JobCandidateBoard } from "@/components/jobs/job-candidate-board";
import { JobCandidateList } from "@/components/jobs/job-candidate-list";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Typography } from "@/components/ui/typography";
import { cn, skillHueClass } from "@/lib/utils";

const statusDotClass: Record<string, string> = {
  open: "bg-success",
  draft: "bg-warning",
  closed: "bg-muted-foreground",
  archived: "bg-destructive",
};

// Mirrors the backend lifecycle rules (JobService._ALLOWED_TRANSITIONS) so
// the menu only offers legal next states. The backend still validates —
// this is a UX shortcut, not the source of truth. Archived is terminal.
const jobStatusTransitions: Record<JobStatus, JobStatus[]> = {
  draft: ["open", "archived"],
  open: ["closed", "archived"],
  closed: ["open", "archived"],
  archived: [],
};

const statusLabel: Record<JobStatus, string> = {
  draft: "Draft",
  open: "Open",
  closed: "Closed",
  archived: "Archived",
};

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [viewMode, setViewMode] = React.useState<"list" | "kanban">("list");
  // Filters live here (not inside each view) so toggling list ↔
  // kanban preserves the active search / score tier / status set /
  // saved view. Each view still owns its own sort, selection, and
  // drawer state.
  const filters = useCandidateFilters();

  const {
    data: job,
    isLoading,
    isError,
  } = useQuery({
    ...getJobOptions({ path: { job_id: id ?? "" } }),
    enabled: Boolean(id),
  });

  const { data: applications = [], isLoading: appsLoading } = useQuery({
    ...listJobApplicationsOptions({ path: { job_id: id ?? "" } }),
    enabled: Boolean(id && job),
    select: (data): ApplicationResponse[] => data ?? [],
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteJob({ path: { job_id: id ?? "" } }),
    onSuccess: () => {
      toast.success(`${job?.title ?? "Job"} deleted`);
      navigate("/jobs");
    },
    onError: () => {
      toast.error("Couldn't delete the job");
    },
  });

  // Re-scores every candidate in the pool against this job. Idempotent
  // per candidate: existing applications update in place, missing
  // ones are created. Invalidates the list so fresh scores land.
  const matchMut = useMutation({
    ...matchCandidatesMutation(),
    onSuccess: (data) => {
      const count = data?.total ?? 0;
      toast.success(
        count === 0
          ? "No candidates to match yet. Upload resumes first."
          : `Scored ${count} candidate${count === 1 ? "" : "s"}.`
      );
      queryClient.invalidateQueries({
        queryKey: listJobApplicationsQueryKey({ path: { job_id: id ?? "" } }),
      });
    },
    onError: () => {
      toast.error("Match run failed.");
    },
  });

  const runMatch = React.useCallback(() => {
    if (!id) return;
    matchMut.mutate({ path: { job_id: id } });
  }, [id, matchMut]);

  const onStatusChanged = React.useCallback(() => {
    // Keep the list cache fresh after a row-level status change. We
    // optimistic-update inside the list component; this invalidation
    // just guarantees eventual consistency if the user navigates away
    // and back.
    queryClient.invalidateQueries({
      queryKey: listJobApplicationsQueryKey({ path: { job_id: id ?? "" } }),
    });
  }, [queryClient, id]);

  if (!id) {
    navigate("/jobs", { replace: true });
    return null;
  }

  if (isLoading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <Loader2Icon className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  if (isError || !job) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <Typography variant="h4">Job not found</Typography>
        <Typography variant="muted">
          It may have been deleted, or you don&apos;t have access.
        </Typography>
        <Link to="/jobs">
          <Button variant="outline">
            <ArrowLeftIcon className="size-4" data-icon="inline-start" />
            Back to jobs
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/jobs")}
          aria-label="Back to jobs"
        >
          <ArrowLeftIcon className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Typography variant="h3" className="truncate">
              {job.title}
            </Typography>
            <JobStatusControl job={job} />
          </div>
          <Typography variant="muted" className="mt-1 text-sm">
            {job.location || "No location"} &middot; Min {job.experience_min}
            {job.experience_max ? `–${job.experience_max}` : "+"} yr
          </Typography>
          {job.required_skills.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {job.required_skills.map((skill) => (
                <Badge
                  key={skill}
                  variant="outline"
                  className={cn("text-xs", skillHueClass(skill))}
                >
                  {skill}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            onClick={runMatch}
            disabled={matchMut.isPending}
          >
            <SparklesIcon
              className={`size-4 ${matchMut.isPending ? "animate-pulse" : ""}`}
              data-icon="inline-start"
            />
            {matchMut.isPending ? "Scoring…" : "Refresh scores"}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" size="icon" aria-label="More actions">
                  <MoreHorizontalIcon className="size-4" />
                </Button>
              }
            />
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() => navigate(`/jobs/${job.id}/edit`)}
              >
                <PencilIcon className="mr-2 size-4" />
                Edit job
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive"
                onClick={() => setConfirmDelete(true)}
              >
                <TrashIcon className="mr-2 size-4" />
                Delete job
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {applications.length > 0 && (
        <CandidateFilterBar
          api={filters}
          totalCount={applications.length}
          filteredCount={
            applyCandidateFilters(applications, filters.state).length
          }
          rightSlot={
            <ToggleGroup
              variant="outline"
              value={[viewMode]}
              onValueChange={(value) => {
                const next = Array.isArray(value) ? value[0] : value;
                if (next === "list" || next === "kanban") setViewMode(next);
              }}
              aria-label="View mode"
            >
              <ToggleGroupItem value="list" aria-label="List view">
                <ListIcon className="size-4" data-icon="inline-start" />
                List
              </ToggleGroupItem>
              <ToggleGroupItem value="kanban" aria-label="Kanban view">
                <LayoutGridIcon className="size-4" data-icon="inline-start" />
                Kanban
              </ToggleGroupItem>
            </ToggleGroup>
          }
        />
      )}

      {appsLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Loader2Icon className="text-muted-foreground size-5 animate-spin" />
        </div>
      ) : applications.length === 0 ? (
        <EmptyCandidates onRunMatch={runMatch} pending={matchMut.isPending} />
      ) : (
        <CandidateViewContent
          applications={applications}
          filters={filters}
          viewMode={viewMode}
          onStatusChanged={onStatusChanged}
        />
      )}

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this job?</AlertDialogTitle>
            <AlertDialogDescription>
              All {applications.length} applications associated with&nbsp;
              <span className="font-medium">{job.title}</span> will be removed
              too. This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground"
              onClick={() => deleteMut.mutate()}
            >
              Delete job
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function JobStatusControl({ job }: { job: JobResponse }) {
  const queryClient = useQueryClient();
  const [pendingArchive, setPendingArchive] = React.useState(false);

  const statusMut = useMutation({
    ...changeJobStatusMutation(),
    onSuccess: (updated) => {
      toast.success(`Status set to ${statusLabel[updated.status]}`);
      queryClient.invalidateQueries({
        queryKey: getJobQueryKey({ path: { job_id: job.id } }),
      });
    },
    onError: (error) => {
      const message =
        (error as ErrorResponse | undefined)?.error?.message ??
        "Couldn't change status";
      toast.error(message);
    },
  });

  const change = (status: JobStatus) =>
    statusMut.mutate({ path: { job_id: job.id }, body: { status } });

  const actionLabel = (target: JobStatus) => {
    if (target === "open")
      return job.status === "closed" ? "Reopen job" : "Open job";
    if (target === "closed") return "Close job";
    if (target === "archived") return "Archive job";
    return statusLabel[target];
  };

  const nextStates = jobStatusTransitions[job.status];

  // Archived is terminal — nothing to transition to, so show a plain badge.
  if (nextStates.length === 0) {
    return (
      <Badge variant="outline" className="capitalize">
        {job.status}
      </Badge>
    );
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="outline"
              size="sm"
              disabled={statusMut.isPending}
              className="h-7 gap-1.5 capitalize"
            >
              <span
                aria-hidden
                className={cn(
                  "inline-block size-2 rounded-full",
                  statusDotClass[job.status] ?? "bg-muted-foreground"
                )}
              />
              {job.status}
              <ChevronDownIcon className="size-3.5 opacity-60" />
            </Button>
          }
        />
        <DropdownMenuContent align="start">
          {nextStates.map((target) => (
            <DropdownMenuItem
              key={target}
              className={target === "archived" ? "text-destructive" : undefined}
              onClick={() =>
                target === "archived" ? setPendingArchive(true) : change(target)
              }
            >
              <span
                aria-hidden
                className={cn(
                  "mr-2 inline-block size-2 rounded-full",
                  statusDotClass[target] ?? "bg-muted-foreground"
                )}
              />
              {actionLabel(target)}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={pendingArchive} onOpenChange={setPendingArchive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive this job?</AlertDialogTitle>
            <AlertDialogDescription>
              Archiving is permanent — an archived job can&apos;t be reopened.
              Create a new job if you need to hire for this role again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground"
              onClick={() => change("archived")}
            >
              Archive job
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function CandidateViewContent({
  applications,
  filters,
  viewMode,
  onStatusChanged,
}: {
  applications: ApplicationResponse[];
  filters: ReturnType<typeof useCandidateFilters>;
  viewMode: "list" | "kanban";
  onStatusChanged: () => void;
}) {
  const filtered = React.useMemo(
    () => applyCandidateFilters(applications, filters.state),
    [applications, filters.state]
  );

  if (filtered.length === 0) {
    return <EmptyFiltersState api={filters} />;
  }

  return viewMode === "kanban" ? (
    <JobCandidateBoard
      applications={filtered}
      onStatusChanged={onStatusChanged}
    />
  ) : (
    <JobCandidateList
      applications={filtered}
      onStatusChanged={onStatusChanged}
      searchInputRef={filters.searchInputRef}
    />
  );
}

function EmptyCandidates({
  onRunMatch,
  pending,
}: {
  onRunMatch: () => void;
  pending: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
      <div className="bg-cat-4/10 flex size-16 items-center justify-center rounded">
        <BriefcaseIcon className="text-cat-4 size-8" />
      </div>
      <Typography variant="h5" className="mt-4 max-w-[32ch]">
        No candidates matched yet.
      </Typography>
      <Typography variant="muted" className="mt-1 max-w-[48ch]">
        Run a match to score your candidate pool against this job&rsquo;s
        requirements. Matching creates applications you can shortlist or reject
        here.
      </Typography>
      <Button className="mt-4" onClick={onRunMatch} disabled={pending}>
        <SparklesIcon
          className={`size-4 ${pending ? "animate-pulse" : ""}`}
          data-icon="inline-start"
        />
        {pending ? "Scoring candidates…" : "Run match"}
      </Button>
    </div>
  );
}
