import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  BriefcaseIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
} from "lucide-react";

import { listJobsOptions, deleteJob, type JobResponse } from "@/api";
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
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Typography } from "@/components/ui/typography";
import { formatDate } from "@/lib/utils";
import { toast } from "sonner";

const statusVariant: Record<
  string,
  "default" | "secondary" | "outline" | "destructive"
> = {
  open: "default",
  draft: "outline",
  closed: "secondary",
  archived: "destructive",
};

export function JobsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = React.useState<JobResponse | null>(
    null
  );

  const { data: jobs = [], isLoading } = useQuery({
    ...listJobsOptions(),
    select: (data) => data ?? [],
  });

  const deleteMut = useMutation({
    mutationFn: (job: JobResponse) => deleteJob({ path: { job_id: job.id } }),
    onSuccess: (_, job) => {
      toast.success(`${job.title} deleted`);
      queryClient.invalidateQueries({ queryKey: listJobsOptions().queryKey });
    },
    onError: (_, job) => {
      toast.error(`Couldn't delete ${job.title}`, {
        action: {
          label: "Retry",
          onClick: () => deleteMut.mutate(job),
        },
      });
    },
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-8 w-28" />
            <Skeleton className="h-4 w-72" />
          </div>
          <Skeleton className="h-10 w-28" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="space-y-3 border p-4">
              <div className="flex items-start justify-between">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="size-8 shrink-0" />
              </div>
              <Skeleton className="h-4 w-2/3" />
              <div className="flex flex-wrap gap-1.5 pt-1">
                <Skeleton className="h-5 w-16" />
                <Skeleton className="h-5 w-20" />
                <Skeleton className="h-5 w-14" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <Typography variant="h3">Jobs</Typography>
          <Typography variant="muted">
            Manage your job postings and match candidates
          </Typography>
        </div>
        <Button onClick={() => navigate("/jobs/create")}>
          <PlusIcon className="size-4" data-icon="inline-start" />
          Create Job
        </Button>
      </div>

      {jobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <BriefcaseIcon className="text-muted-foreground size-12" />
          <Typography variant="h4" className="mt-4">
            No jobs yet
          </Typography>
          <Typography variant="muted" className="mt-1">
            Create your first job posting to start screening candidates
          </Typography>
          <Button className="mt-4" onClick={() => navigate("/jobs/create")}>
            <PlusIcon className="size-4" data-icon="inline-start" />
            Create Job
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => (
            <Card key={job.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <Typography variant="h6">{job.title}</Typography>
                    <Typography variant="muted">
                      {job.location || "No location"} · Min {job.experience_min}
                      yr
                    </Typography>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm">
                        <MoreHorizontalIcon className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={() => navigate(`/jobs/${job.id}/edit`)}
                      >
                        <PencilIcon className="mr-2 size-4" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={() => setConfirmDelete(job)}
                      >
                        <TrashIcon className="mr-2 size-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1">
                  {job.required_skills.slice(0, 4).map((skill) => (
                    <Badge key={skill} variant="secondary" className="text-xs">
                      {skill}
                    </Badge>
                  ))}
                  {job.required_skills.length > 4 && (
                    <Badge variant="outline" className="text-xs">
                      +{job.required_skills.length - 4}
                    </Badge>
                  )}
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <Badge
                    variant={statusVariant[job.status] ?? "outline"}
                    className="capitalize"
                  >
                    {job.status}
                  </Badge>
                  <Typography variant="muted" className="text-xs">
                    {formatDate(job.created_at)}
                  </Typography>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <AlertDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this job?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete?.title} will be removed, along with any candidate
              matches. This can&rsquo;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (confirmDelete) deleteMut.mutate(confirmDelete);
                setConfirmDelete(null);
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
