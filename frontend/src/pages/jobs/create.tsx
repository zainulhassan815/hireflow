import { useNavigate } from "react-router-dom";
import { ArrowLeftIcon } from "lucide-react";

import { createJob } from "@/api";
import { Button } from "@/components/ui/button";
import { Typography } from "@/components/ui/typography";
import { JobForm, type JobFormData } from "@/components/jobs/job-form";
import { toast } from "sonner";

export function CreateJobPage() {
  const navigate = useNavigate();

  const handleSubmit = async (data: JobFormData) => {
    const { error } = await createJob({
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
      const message =
        typeof error === "object" && "detail" in error
          ? (error as { detail: string }).detail
          : "Failed to create job";
      toast.error(message);
      return;
    }
    toast.success("Job created successfully");
    navigate("/jobs");
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate("/jobs")}>
          <ArrowLeftIcon className="size-4" />
        </Button>
        <div>
          <Typography variant="h3">Create Job</Typography>
          <Typography variant="muted">
            Create a new job posting with requirements
          </Typography>
        </div>
      </div>

      {/* Form */}
      <JobForm
        onSubmit={handleSubmit}
        onCancel={() => navigate("/jobs")}
        submitLabel="Create Job"
      />
    </div>
  );
}
