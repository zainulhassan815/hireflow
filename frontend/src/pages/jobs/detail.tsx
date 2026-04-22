import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  BriefcaseIcon,
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
  deleteJob,
  getJobOptions,
  listJobApplicationsOptions,
  listJobApplicationsQueryKey,
  matchCandidatesMutation,
  type ApplicationResponse,
} from "@/api";
import { CandidateDrawer } from "@/components/jobs/candidate-drawer";
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Typography } from "@/components/ui/typography";
import { cn, skillHueClass } from "@/lib/utils";

const statusDotClass: Record<string, string> = {
  open: "bg-success",
  draft: "bg-warning",
  closed: "bg-muted-foreground",
  archived: "bg-destructive",
};

/**
 * F44.b — job detail page at `/jobs/:id`.
 *
 * Header: title + status dot, required-skills chips, Edit / Delete.
 * Body: JobCandidateList renders the application rows with match score
 * bars and inline shortlist/reject/undo buttons. This page is the
 * primary landing spot for a job now; `/jobs/:id/edit` still exists
 * but is reachable from the Edit button here.
 */
export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  // F44.d.4 — which application is currently being peeked in the
  // slide-over drawer. Setting to null closes the drawer.
  const [drawerApp, setDrawerApp] = React.useState<ApplicationResponse | null>(
    null
  );

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

  // F44.c — re-score every candidate in the pool against this job.
  // Idempotent per candidate: existing applications update in place,
  // missing ones get created. Invalidates the list so fresh scores
  // repopulate the table.
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
      {/* Header */}
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
            <span
              aria-hidden
              className={cn(
                "inline-block size-2 shrink-0 rounded-full",
                statusDotClass[job.status] ?? "bg-muted-foreground"
              )}
            />
            <Typography variant="h3" className="truncate">
              {job.title}
            </Typography>
            <Badge variant="outline" className="capitalize">
              {job.status}
            </Badge>
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

      {/* View toggle — F44.d.3. Kanban disabled until F93 ships. */}
      {applications.length > 0 && (
        <div className="flex justify-end">
          <ToggleGroup
            variant="outline"
            value={["list"]}
            aria-label="View mode"
          >
            <ToggleGroupItem value="list" aria-label="List view">
              <ListIcon className="size-4" data-icon="inline-start" />
              List
            </ToggleGroupItem>
            <Tooltip>
              <TooltipTrigger
                render={
                  <ToggleGroupItem
                    value="kanban"
                    aria-label="Kanban view"
                    disabled
                  >
                    <LayoutGridIcon
                      className="size-4"
                      data-icon="inline-start"
                    />
                    Kanban
                  </ToggleGroupItem>
                }
              />
              <TooltipContent>Coming in F93</TooltipContent>
            </Tooltip>
          </ToggleGroup>
        </div>
      )}

      {/* Candidate list */}
      {appsLoading ? (
        <div className="flex h-48 items-center justify-center">
          <Loader2Icon className="text-muted-foreground size-5 animate-spin" />
        </div>
      ) : applications.length === 0 ? (
        <EmptyCandidates onRunMatch={runMatch} pending={matchMut.isPending} />
      ) : (
        <JobCandidateList
          applications={applications}
          onStatusChanged={onStatusChanged}
          onOpenCandidate={setDrawerApp}
        />
      )}

      {/* Drawer — mirror the freshest application from the list cache
          so status changes outside the drawer stay in sync while it's
          open (optimistic updates from the row-level mutation, bulk
          actions, refetches after "Refresh scores", etc.). */}
      <CandidateDrawer
        app={
          drawerApp
            ? (applications.find((a) => a.id === drawerApp.id) ?? drawerApp)
            : null
        }
        onOpenChange={(open) => {
          if (!open) setDrawerApp(null);
        }}
        onStatusChanged={onStatusChanged}
      />

      {/* Delete confirm */}
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
