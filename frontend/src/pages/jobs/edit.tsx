import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeftIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Typography } from "@/components/ui/typography";
import { JobForm, type JobFormData } from "@/components/jobs/job-form";
import { toast } from "sonner";

// Mock data - would be fetched from API
const mockJobData: JobFormData = {
  title: "Senior Frontend Developer",
  department: "engineering",
  location: "Remote",
  employmentType: "full-time",
  description:
    "We are looking for a Senior Frontend Developer to join our team...",
  requiredSkills: ["React", "TypeScript", "CSS"],
  preferredSkills: ["Node.js", "GraphQL"],
  educationLevel: "bachelors",
  experienceMin: 3,
  experienceMax: 7,
  salaryMin: 80000,
  salaryMax: 120000,
  status: "active",
};

export function EditJobPage() {
  const navigate = useNavigate();
  const { id } = useParams();

  const handleSubmit = async (data: JobFormData) => {
    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 500));
    console.log("Updating job:", id, data);
    toast.success("Job updated successfully");
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
          <Typography variant="h3">Edit Job</Typography>
          <Typography variant="muted">Update job posting details</Typography>
        </div>
      </div>

      {/* Form */}
      <JobForm
        initialData={mockJobData}
        onSubmit={handleSubmit}
        onCancel={() => navigate("/jobs")}
        submitLabel="Update Job"
      />
    </div>
  );
}
