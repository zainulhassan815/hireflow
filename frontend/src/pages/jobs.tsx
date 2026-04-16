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
import { Spinner } from "@/components/ui/spinner";
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
    onError: () => toast.error("Failed to delete job"),
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Spinner className="size-8" />
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
                        onClick={() => deleteMut.mutate(job)}
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
    </div>
  );
}
