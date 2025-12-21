import {
  BriefcaseIcon,
  FileTextIcon,
  ClockIcon,
  MoreVerticalIcon,
  SearchIcon,
  TrendingDownIcon,
  TrendingUpIcon,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Typography } from "@/components/ui/typography";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const stats = [
  {
    title: "Active Jobs",
    value: "12",
    trend: "+2 this week",
    trendUp: true,
    icon: BriefcaseIcon,
  },
  {
    title: "Total Applications",
    value: "1,240",
    trend: "+12% this week",
    trendUp: true,
    icon: FileTextIcon,
  },
  {
    title: "Pending Reviews",
    value: "45",
    trend: "-5 this week",
    trendUp: false,
    icon: ClockIcon,
  },
];

type ApplicationStatus = "top_pick" | "review" | "processing" | "interview";

const recentApplications: {
  id: number;
  name: string;
  initials: string;
  job: string;
  department: string;
  appliedAt: string;
  matchScore: number | null;
  status: ApplicationStatus;
}[] = [
  {
    id: 1,
    name: "Sarah Jenkins",
    initials: "SJ",
    job: "UX Designer",
    department: "Design",
    appliedAt: "2h ago",
    matchScore: 94,
    status: "top_pick",
  },
  {
    id: 2,
    name: "Michael Chen",
    initials: "MC",
    job: "Senior Frontend Dev",
    department: "Engineering",
    appliedAt: "4h ago",
    matchScore: 78,
    status: "review",
  },
  {
    id: 3,
    name: "Emily Davis",
    initials: "ED",
    job: "Product Manager",
    department: "Product",
    appliedAt: "5h ago",
    matchScore: null,
    status: "processing",
  },
  {
    id: 4,
    name: "David Kim",
    initials: "DK",
    job: "Data Scientist",
    department: "Analytics",
    appliedAt: "1d ago",
    matchScore: 88,
    status: "interview",
  },
  {
    id: 5,
    name: "Lisa Wang",
    initials: "LW",
    job: "Backend Engineer",
    department: "Engineering",
    appliedAt: "1d ago",
    matchScore: 91,
    status: "top_pick",
  },
];

const statusConfig: Record<
  ApplicationStatus,
  { label: string; className: string }
> = {
  top_pick: {
    label: "Top Pick",
    className:
      "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  },
  review: {
    label: "Review",
    className:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  processing: {
    label: "Processing",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  },
  interview: {
    label: "Interview",
    className:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  },
};

export function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      {/* Header & Search */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">Dashboard</Typography>
          <Typography variant="muted">
            Overview of your recruitment pipeline
          </Typography>
        </div>
        <div className="w-full sm:w-80">
          <div className="relative">
            <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
            <Input
              placeholder="Search candidates..."
              className="h-9 pr-12 pl-9"
            />
            <kbd className="text-muted-foreground absolute top-1/2 right-3 -translate-y-1/2 text-xs">
              ⌘K
            </kbd>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {stats.map((stat) => (
          <Card key={stat.title} className="border">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <Typography variant="muted" as="span">
                  {stat.title}
                </Typography>
                <stat.icon className="text-muted-foreground size-4" />
              </div>
              <Typography variant="h3" className="mt-2">
                {stat.value}
              </Typography>
              <div className="mt-1 flex items-center gap-1">
                {stat.trendUp ? (
                  <TrendingUpIcon className="size-3 text-green-600" />
                ) : (
                  <TrendingDownIcon className="size-3 text-red-600" />
                )}
                <Typography
                  variant="small"
                  as="span"
                  className={stat.trendUp ? "text-green-600" : "text-red-600"}
                >
                  {stat.trend}
                </Typography>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent Applications */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <Typography variant="h5">Recent Applications</Typography>
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            View All
          </Button>
        </div>
        <Card className="border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Candidate</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Match Score</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentApplications.map((application) => (
                <TableRow key={application.id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className="bg-muted flex size-8 items-center justify-center text-xs font-medium">
                        {application.initials}
                      </div>
                      <div>
                        <Typography variant="small" className="font-medium">
                          {application.name}
                        </Typography>
                        <Typography variant="muted" className="text-xs">
                          {application.appliedAt}
                        </Typography>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Typography variant="small">{application.job}</Typography>
                    <Typography variant="muted" className="text-xs">
                      {application.department}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {application.matchScore !== null ? (
                      <div className="flex items-center gap-2">
                        <Progress
                          value={application.matchScore}
                          className="h-1.5 w-16"
                        />
                        <Typography variant="small" className="font-medium">
                          {application.matchScore}%
                        </Typography>
                      </div>
                    ) : (
                      <Typography variant="muted">Processing...</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium ${
                        statusConfig[application.status].className
                      }`}
                    >
                      {statusConfig[application.status].label}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="size-8">
                      <MoreVerticalIcon className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </div>
    </div>
  );
}
