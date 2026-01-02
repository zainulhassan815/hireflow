import * as React from "react";
import {
  CheckIcon,
  DownloadIcon,
  EyeIcon,
  FilterIcon,
  MoreHorizontalIcon,
  SearchIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  XIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { ResumeViewer } from "@/components/candidates/resume-viewer";
import { toast } from "sonner";

type CandidateStatus = "new" | "reviewed" | "shortlisted" | "rejected";

interface Candidate {
  id: string;
  name: string;
  email: string;
  job: string;
  status: CandidateStatus;
  matchScore: number;
  appliedAt: string;
  skills: string[];
}

const initialCandidates: Candidate[] = [
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
  const [candidates, setCandidates] =
    React.useState<Candidate[]>(initialCandidates);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [jobFilter, setJobFilter] = React.useState("all");
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [viewingCandidate, setViewingCandidate] =
    React.useState<Candidate | null>(null);

  const filteredCandidates = candidates.filter((candidate) => {
    const matchesSearch =
      candidate.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      candidate.email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesJob = jobFilter === "all" || candidate.job.includes(jobFilter);
    const matchesStatus =
      statusFilter === "all" || candidate.status === statusFilter;
    return matchesSearch && matchesJob && matchesStatus;
  });

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(filteredCandidates.map((c) => c.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const newSelected = new Set(selectedIds);
    if (checked) {
      newSelected.add(id);
    } else {
      newSelected.delete(id);
    }
    setSelectedIds(newSelected);
  };

  const updateCandidateStatus = (id: string, status: CandidateStatus) => {
    setCandidates((prev) =>
      prev.map((c) => (c.id === id ? { ...c, status } : c))
    );
  };

  const handleShortlist = (id: string) => {
    updateCandidateStatus(id, "shortlisted");
    toast.success("Candidate shortlisted");
    setViewingCandidate(null);
  };

  const handleReject = (id: string) => {
    updateCandidateStatus(id, "rejected");
    toast.success("Candidate rejected");
    setViewingCandidate(null);
  };

  const handleBulkShortlist = () => {
    selectedIds.forEach((id) => {
      updateCandidateStatus(id, "shortlisted");
    });
    toast.success(`${selectedIds.size} candidates shortlisted`);
    setSelectedIds(new Set());
  };

  const handleBulkReject = () => {
    selectedIds.forEach((id) => {
      updateCandidateStatus(id, "rejected");
    });
    toast.success(`${selectedIds.size} candidates rejected`);
    setSelectedIds(new Set());
  };

  const handleExport = () => {
    const dataToExport =
      selectedIds.size > 0
        ? candidates.filter((c) => selectedIds.has(c.id))
        : candidates.filter((c) => c.status === "shortlisted");

    console.log("Exporting candidates:", dataToExport);
    toast.success(`Exported ${dataToExport.length} candidates to Excel`);
  };

  const allSelected =
    filteredCandidates.length > 0 &&
    filteredCandidates.every((c) => selectedIds.has(c.id));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <Typography variant="h3">Candidates</Typography>
          <Typography variant="muted">
            View and manage all job applicants
          </Typography>
        </div>
        <Button variant="outline" onClick={handleExport}>
          <DownloadIcon className="size-4" data-icon="inline-start" />
          Export to Excel
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative max-w-sm min-w-[200px] flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            placeholder="Search candidates..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={jobFilter} onValueChange={setJobFilter}>
          <SelectTrigger className="w-[180px]">
            <span className="text-muted-foreground">
              {jobFilter === "all" ? "All Jobs" : jobFilter}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Jobs</SelectItem>
            <SelectItem value="Frontend">Senior Frontend Developer</SelectItem>
            <SelectItem value="Backend">Backend Engineer</SelectItem>
            <SelectItem value="DevOps">DevOps Engineer</SelectItem>
            <SelectItem value="Product">Product Manager</SelectItem>
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[150px]">
            <span className="text-muted-foreground">
              {statusFilter === "all" ? "All Status" : statusFilter}
            </span>
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

      {/* Bulk Actions */}
      {selectedIds.size > 0 && (
        <div className="bg-muted/50 flex items-center gap-4 rounded-lg border p-3">
          <Typography variant="small" className="font-medium">
            {selectedIds.size} selected
          </Typography>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={handleBulkShortlist}>
              <ThumbsUpIcon className="size-4" data-icon="inline-start" />
              Shortlist Selected
            </Button>
            <Button size="sm" variant="outline" onClick={handleBulkReject}>
              <ThumbsDownIcon className="size-4" data-icon="inline-start" />
              Reject Selected
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelectedIds(new Set())}
            >
              <XIcon className="size-4" data-icon="inline-start" />
              Clear
            </Button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={handleSelectAll}
                />
              </TableHead>
              <TableHead>Candidate</TableHead>
              <TableHead>Job</TableHead>
              <TableHead>Skills</TableHead>
              <TableHead>Match Score</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Applied</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredCandidates.map((candidate) => (
              <TableRow
                key={candidate.id}
                className="cursor-pointer"
                onClick={() => setViewingCandidate(candidate)}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selectedIds.has(candidate.id)}
                    onCheckedChange={(checked) =>
                      handleSelectOne(candidate.id, !!checked)
                    }
                  />
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <div className="bg-muted flex size-8 items-center justify-center rounded-full text-xs font-medium">
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
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm">
                        <MoreHorizontalIcon className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={() => setViewingCandidate(candidate)}
                      >
                        <EyeIcon className="mr-2 size-4" />
                        View Resume
                      </DropdownMenuItem>
                      {candidate.status !== "shortlisted" && (
                        <DropdownMenuItem
                          onClick={() => handleShortlist(candidate.id)}
                        >
                          <CheckIcon className="mr-2 size-4" />
                          Shortlist
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuSeparator />
                      {candidate.status !== "rejected" && (
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => handleReject(candidate.id)}
                        >
                          <XIcon className="mr-2 size-4" />
                          Reject
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Resume Viewer Modal */}
      <ResumeViewer
        candidate={viewingCandidate}
        open={!!viewingCandidate}
        onOpenChange={(open) => !open && setViewingCandidate(null)}
        onShortlist={() =>
          viewingCandidate && handleShortlist(viewingCandidate.id)
        }
        onReject={() => viewingCandidate && handleReject(viewingCandidate.id)}
      />
    </div>
  );
}
