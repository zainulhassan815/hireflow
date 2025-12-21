import { Link } from "react-router-dom";
import { MoreHorizontalIcon, PlusIcon, UsersIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
          <p className="text-muted-foreground">
            Manage your job postings and view applicants
          </p>
        </div>
        <Button>
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
                  <CardTitle className="text-base">
                    <Link to={`/jobs/${job.id}`} className="hover:underline">
                      {job.title}
                    </Link>
                  </CardTitle>
                  <CardDescription>
                    {job.department} · {job.location}
                  </CardDescription>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger>
                    <Button variant="ghost" size="icon-sm">
                      <MoreHorizontalIcon className="size-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem>Edit</DropdownMenuItem>
                    <DropdownMenuItem>View Applications</DropdownMenuItem>
                    <DropdownMenuItem>Duplicate</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem className="text-destructive">
                      Close Job
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
                  <span className="text-muted-foreground text-sm">
                    {job.type}
                  </span>
                </div>
                <div className="text-muted-foreground flex items-center gap-1 text-sm">
                  <UsersIcon className="size-4" />
                  {job.applicants}
                </div>
              </div>
              <p className="text-muted-foreground mt-3 text-xs">
                Posted {new Date(job.postedAt).toLocaleDateString()}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
