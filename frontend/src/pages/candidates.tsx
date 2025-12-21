import { FilterIcon, SearchIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { Typography } from "@/components/ui/typography";

type CandidateStatus = "new" | "reviewed" | "shortlisted" | "rejected";

const candidates: {
  id: string;
  name: string;
  email: string;
  job: string;
  status: CandidateStatus;
  matchScore: number;
  appliedAt: string;
  skills: string[];
}[] = [
  {
    id: "1",
    name: "Sarah Johnson",
    email: "sarah.johnson@email.com",
    job: "Senior Frontend Developer",
    status: "shortlisted",
    matchScore: 92,
    appliedAt: "2024-01-15",
    skills: ["React", "TypeScript", "Node.js"],
  },
  {
    id: "2",
    name: "Michael Chen",
    email: "michael.chen@email.com",
    job: "Backend Engineer",
    status: "reviewed",
    matchScore: 87,
    appliedAt: "2024-01-14",
    skills: ["Python", "PostgreSQL", "AWS"],
  },
  {
    id: "3",
    name: "Emily Davis",
    email: "emily.davis@email.com",
    job: "Senior Frontend Developer",
    status: "new",
    matchScore: 95,
    appliedAt: "2024-01-13",
    skills: ["React", "Vue.js", "CSS"],
  },
  {
    id: "4",
    name: "James Wilson",
    email: "james.wilson@email.com",
    job: "DevOps Engineer",
    status: "new",
    matchScore: 78,
    appliedAt: "2024-01-12",
    skills: ["Docker", "Kubernetes", "Terraform"],
  },
  {
    id: "5",
    name: "Lisa Anderson",
    email: "lisa.anderson@email.com",
    job: "Product Manager",
    status: "rejected",
    matchScore: 45,
    appliedAt: "2024-01-11",
    skills: ["Agile", "Jira", "Analytics"],
  },
  {
    id: "6",
    name: "David Brown",
    email: "david.brown@email.com",
    job: "Backend Engineer",
    status: "shortlisted",
    matchScore: 89,
    appliedAt: "2024-01-10",
    skills: ["Go", "Redis", "gRPC"],
  },
  {
    id: "7",
    name: "Jennifer Martinez",
    email: "jennifer.martinez@email.com",
    job: "Senior Frontend Developer",
    status: "reviewed",
    matchScore: 82,
    appliedAt: "2024-01-09",
    skills: ["Angular", "RxJS", "SCSS"],
  },
];

const statusVariant: Record<
  CandidateStatus,
  "default" | "secondary" | "outline" | "destructive"
> = {
  new: "default",
  reviewed: "secondary",
  shortlisted: "outline",
  rejected: "destructive",
};

export function CandidatesPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Typography variant="h3">Candidates</Typography>
        <Typography variant="muted">
          View and manage all job applicants
        </Typography>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative max-w-sm min-w-[200px] flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input placeholder="Search candidates..." className="pl-9" />
        </div>
        <Select>
          <SelectTrigger className="w-[180px]">
            <span className="text-muted-foreground">All Jobs</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Jobs</SelectItem>
            <SelectItem value="frontend">Senior Frontend Developer</SelectItem>
            <SelectItem value="backend">Backend Engineer</SelectItem>
            <SelectItem value="devops">DevOps Engineer</SelectItem>
            <SelectItem value="pm">Product Manager</SelectItem>
          </SelectContent>
        </Select>
        <Select>
          <SelectTrigger className="w-[150px]">
            <span className="text-muted-foreground">All Status</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="reviewed">Reviewed</SelectItem>
            <SelectItem value="shortlisted">Shortlisted</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm">
          <FilterIcon className="size-4" data-icon="inline-start" />
          More Filters
        </Button>
      </div>

      {/* Table */}
      <div className="border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Candidate</TableHead>
              <TableHead>Job</TableHead>
              <TableHead>Skills</TableHead>
              <TableHead>Match Score</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Applied</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {candidates.map((candidate) => (
              <TableRow key={candidate.id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <div className="bg-muted flex size-8 items-center justify-center text-xs font-medium">
                      {candidate.name
                        .split(" ")
                        .map((n) => n[0])
                        .join("")}
                    </div>
                    <div>
                      <Typography variant="small" className="font-medium">
                        {candidate.name}
                      </Typography>
                      <Typography variant="muted" className="text-xs">
                        {candidate.email}
                      </Typography>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Typography variant="small">{candidate.job}</Typography>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {candidate.skills.slice(0, 2).map((skill) => (
                      <Badge
                        key={skill}
                        variant="secondary"
                        className="text-xs"
                      >
                        {skill}
                      </Badge>
                    ))}
                    {candidate.skills.length > 2 && (
                      <Badge variant="outline" className="text-xs">
                        +{candidate.skills.length - 2}
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Progress
                      value={candidate.matchScore}
                      className="h-1.5 w-16"
                    />
                    <Typography variant="small" className="font-medium">
                      {candidate.matchScore}%
                    </Typography>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant[candidate.status]}>
                    {candidate.status}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Typography variant="muted">
                    {new Date(candidate.appliedAt).toLocaleDateString()}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
