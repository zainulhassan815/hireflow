import { useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, Loader2Icon } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { getJobOptions, updateJob, type JobResponse } from "@/api";
import { JobForm, type JobFormData } from "@/components/jobs/job-form";
import { Button } from "@/components/ui/button";
import { Typography } from "@/components/ui/typography";
import { extractApiError } from "@/lib/api-errors";

function toFormData(job: JobResponse): Partial<JobFormData> {
  return {
    title: job.title,
    location: job.location ?? "",
    description: job.description,
    requiredSkills: job.required_skills,
    preferredSkills: job.preferred_skills ?? [],
    educationLevel: job.education_level ?? "any",
    experienceMin: job.experience_min,
    experienceMax: job.experience_max ?? 0,
  };
}

export function EditJobPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();

  const {
    data: job,
    isLoading,
    isError,
  } = useQuery({
    ...getJobOptions({ path: { job_id: id ?? "" } }),
    enabled: Boolean(id),
  });

  const handleSubmit = async (data: JobFormData) => {
    if (!id) return;
    const { error } = await updateJob({
      path: { job_id: id },
      body: {
        title: data.title,
        description: data.description,
        required_skills: data.requiredSkills,
        preferred_skills:
          data.preferredSkills.length > 0 ? data.preferredSkills : undefined,
        education_level: data.educationLevel || undefined,
        experience_min: data.experienceMin,
        experience_max: data.experienceMax || undefined,
        location: data.location || undefined,
      },
    });
    if (error) {
      toast.error(extractApiError(error).message);
      return;
    }
    toast.success("Job updated");
    navigate(`/jobs/${id}`);
  };

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
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate(`/jobs/${id}`)}
        >
          <ArrowLeftIcon className="size-4" />
        </Button>
        <div>
          <Typography variant="h3">Edit Job</Typography>
          <Typography variant="muted">Update job posting details</Typography>
        </div>
      </div>

      <JobForm
        initialData={toFormData(job)}
        onSubmit={handleSubmit}
        onCancel={() => navigate(`/jobs/${id}`)}
        submitLabel="Update Job"
      />
    </div>
  );
}
