import { useNavigate } from "react-router-dom";
import { ArrowLeftIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Typography } from "@/components/ui/typography";
import { JobForm, type JobFormData } from "@/components/jobs/job-form";
import { toast } from "sonner";

export function CreateJobPage() {
  const navigate = useNavigate();

  const handleSubmit = async (data: JobFormData) => {
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 500));
    console.log("Creating job:", data);
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
