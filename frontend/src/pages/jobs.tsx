import { Link, useNavigate } from "react-router-dom";
import {
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  UsersIcon,
} from "lucide-react";

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
import { Typography } from "@/components/ui/typography";
import { toast } from "sonner";

type JobStatus = "active" | "closed" | "draft";

const jobs: {
  id: string;
  title: string;
  department: string;
  location: string;
  type: string;
  status: JobStatus;
  applicants: number;
  postedAt: string;
}[] = [
  {
    id: "1",
    title: "Senior Frontend Developer",
    department: "Engineering",
    location: "Remote",
    type: "Full-time",
    status: "active",
    applicants: 45,
    postedAt: "2024-01-15",
  },
  {
    id: "2",
    title: "Backend Engineer",
    department: "Engineering",
    location: "New York, NY",
    type: "Full-time",
    status: "active",
    applicants: 32,
    postedAt: "2024-01-10",
  },
  {
    id: "3",
    title: "Product Manager",
    department: "Product",
    location: "San Francisco, CA",
    type: "Full-time",
    status: "active",
    applicants: 28,
    postedAt: "2024-01-08",
  },
  {
    id: "4",
    title: "DevOps Engineer",
    department: "Engineering",
    location: "Remote",
    type: "Full-time",
    status: "active",
    applicants: 19,
    postedAt: "2024-01-05",
  },
  {
    id: "5",
    title: "UI/UX Designer",
    department: "Design",
    location: "Austin, TX",
    type: "Full-time",
    status: "closed",
    applicants: 67,
    postedAt: "2023-12-20",
  },
  {
    id: "6",
    title: "Data Analyst",
    department: "Analytics",
    location: "Remote",
    type: "Contract",
    status: "draft",
    applicants: 0,
    postedAt: "2024-01-18",
  },
];

const statusVariant: Record<JobStatus, "default" | "secondary" | "outline"> = {
  active: "default",
  closed: "secondary",
  draft: "outline",
};

export function JobsPage() {
  const navigate = useNavigate();

  const handleDeleteJob = (jobId: string) => {
    // Mock delete action
    toast.success("Job deleted successfully");
    console.log("Deleting job:", jobId);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <Typography variant="h3">Jobs</Typography>
          <Typography variant="muted">
            Manage your job postings and view applicants
          </Typography>
        </div>
        <Button onClick={() => navigate("/jobs/create")}>
          <PlusIcon className="size-4" data-icon="inline-start" />
          Create Job
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {jobs.map((job) => (
          <Card key={job.id}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <Typography variant="h6">
                    <Link
                      to={`/jobs/${job.id}/edit`}
                      className="hover:underline"
                    >
                      {job.title}
                    </Link>
                  </Typography>
                  <Typography variant="muted">
                    {job.department} · {job.location}
                  </Typography>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger>
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
                    <DropdownMenuItem
                      onClick={() => navigate(`/candidates?job=${job.id}`)}
                    >
                      <UsersIcon className="mr-2 size-4" />
                      View Applicants
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => handleDeleteJob(job.id)}
                    >
                      <TrashIcon className="mr-2 size-4" />
                      Delete Job
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge variant={statusVariant[job.status]}>
                    {job.status}
                  </Badge>
                  <Typography variant="muted" as="span">
                    {job.type}
                  </Typography>
                </div>
                <div className="text-muted-foreground flex items-center gap-1 text-sm">
                  <UsersIcon className="size-4" />
                  {job.applicants}
                </div>
              </div>
              <Typography variant="muted" className="mt-3 text-xs">
                Posted {new Date(job.postedAt).toLocaleDateString()}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
