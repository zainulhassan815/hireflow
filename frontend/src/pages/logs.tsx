import * as React from "react";
import {
  CalendarIcon,
  DownloadIcon,
  FilterIcon,
  RefreshCwIcon,
  SearchIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Typography } from "@/components/ui/typography";

type ActionType =
  | "create"
  | "update"
  | "delete"
  | "login"
  | "upload"
  | "sync"
  | "export";

interface LogEntry {
  id: string;
  timestamp: Date;
  user: string;
  userEmail: string;
  action: ActionType;
  resource: string;
  resourceType: string;
  details?: string;
  ipAddress: string;
}

const mockLogs: LogEntry[] = [
  {
    id: "1",
    timestamp: new Date(Date.now() - 300000),
    user: "Sarah Ahmed",
    userEmail: "sarah@company.com",
    action: "create",
    resource: "Senior Frontend Developer",
    resourceType: "Job",
    details: "Created new job posting",
    ipAddress: "192.168.1.100",
  },
  {
    id: "2",
    timestamp: new Date(Date.now() - 600000),
    user: "Ahmed Khan",
    userEmail: "ahmed@company.com",
    action: "update",
    resource: "John Doe",
    resourceType: "Candidate",
    details: "Status changed to shortlisted",
    ipAddress: "192.168.1.101",
  },
  {
    id: "3",
    timestamp: new Date(Date.now() - 1200000),
    user: "Sarah Ahmed",
    userEmail: "sarah@company.com",
    action: "upload",
    resource: "Resume_Collection.pdf",
    resourceType: "Document",
    details: "Uploaded 5 files",
    ipAddress: "192.168.1.100",
  },
  {
    id: "4",
    timestamp: new Date(Date.now() - 1800000),
    user: "System",
    userEmail: "system@company.com",
    action: "sync",
    resource: "Gmail Integration",
    resourceType: "Email",
    details: "Synced 3 new resumes",
    ipAddress: "127.0.0.1",
  },
  {
    id: "5",
    timestamp: new Date(Date.now() - 3600000),
    user: "Ahmed Khan",
    userEmail: "ahmed@company.com",
    action: "export",
    resource: "Shortlisted Candidates",
    resourceType: "Report",
    details: "Exported 12 candidates to Excel",
    ipAddress: "192.168.1.101",
  },
  {
    id: "6",
    timestamp: new Date(Date.now() - 7200000),
    user: "Sarah Ahmed",
    userEmail: "sarah@company.com",
    action: "login",
    resource: "Dashboard",
    resourceType: "Auth",
    details: "Successful login",
    ipAddress: "192.168.1.100",
  },
  {
    id: "7",
    timestamp: new Date(Date.now() - 10800000),
    user: "Ahmed Khan",
    userEmail: "ahmed@company.com",
    action: "delete",
    resource: "Data Analyst",
    resourceType: "Job",
    details: "Closed job posting",
    ipAddress: "192.168.1.101",
  },
  {
    id: "8",
    timestamp: new Date(Date.now() - 14400000),
    user: "System",
    userEmail: "system@company.com",
    action: "sync",
    resource: "Gmail Integration",
    resourceType: "Email",
    details: "Synced 7 new resumes",
    ipAddress: "127.0.0.1",
  },
  {
    id: "9",
    timestamp: new Date(Date.now() - 86400000),
    user: "Sarah Ahmed",
    userEmail: "sarah@company.com",
    action: "update",
    resource: "Backend Engineer",
    resourceType: "Job",
    details: "Updated job requirements",
    ipAddress: "192.168.1.100",
  },
  {
    id: "10",
    timestamp: new Date(Date.now() - 172800000),
    user: "Ahmed Khan",
    userEmail: "ahmed@company.com",
    action: "create",
    resource: "Product Manager",
    resourceType: "Job",
    details: "Created new job posting",
    ipAddress: "192.168.1.101",
  },
];

const actionConfig: Record<
  ActionType,
  {
    label: string;
    variant: "default" | "secondary" | "outline" | "destructive";
  }
> = {
  create: { label: "Create", variant: "default" },
  update: { label: "Update", variant: "secondary" },
  delete: { label: "Delete", variant: "destructive" },
  login: { label: "Login", variant: "outline" },
  upload: { label: "Upload", variant: "default" },
  sync: { label: "Sync", variant: "secondary" },
  export: { label: "Export", variant: "outline" },
};

export function LogsPage() {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [actionFilter, setActionFilter] = React.useState("all");
  const [userFilter, setUserFilter] = React.useState("all");

  const filteredLogs = mockLogs.filter((log) => {
    const matchesSearch =
      log.resource.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.user.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (log.details?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false);
    const matchesAction = actionFilter === "all" || log.action === actionFilter;
    const matchesUser = userFilter === "all" || log.user === userFilter;
    return matchesSearch && matchesAction && matchesUser;
  });

  const formatTimestamp = (date: Date) => {
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const uniqueUsers = [...new Set(mockLogs.map((log) => log.user))];

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Typography variant="h3">Activity Logs</Typography>
          <Typography variant="muted">
            View system activity and audit trail
          </Typography>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <RefreshCwIcon className="size-4" data-icon="inline-start" />
            Refresh
          </Button>
          <Button variant="outline" size="sm">
            <DownloadIcon className="size-4" data-icon="inline-start" />
            Export Logs
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Total Actions (24h)
            </Typography>
            <Typography variant="h4" className="mt-1">
              {
                mockLogs.filter(
                  (l) => l.timestamp > new Date(Date.now() - 86400000)
                ).length
              }
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Documents Uploaded
            </Typography>
            <Typography variant="h4" className="mt-1">
              {mockLogs.filter((l) => l.action === "upload").length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              Active Users
            </Typography>
            <Typography variant="h4" className="mt-1">
              {uniqueUsers.length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <Typography variant="muted" className="text-xs">
              System Syncs
            </Typography>
            <Typography variant="h4" className="mt-1">
              {mockLogs.filter((l) => l.action === "sync").length}
            </Typography>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative max-w-sm min-w-[200px] flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            placeholder="Search logs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger className="w-[150px]">
            <span className="text-muted-foreground">
              {actionFilter === "all"
                ? "All Actions"
                : actionConfig[actionFilter as ActionType]?.label}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Actions</SelectItem>
            <SelectItem value="create">Create</SelectItem>
            <SelectItem value="update">Update</SelectItem>
            <SelectItem value="delete">Delete</SelectItem>
            <SelectItem value="login">Login</SelectItem>
            <SelectItem value="upload">Upload</SelectItem>
            <SelectItem value="sync">Sync</SelectItem>
            <SelectItem value="export">Export</SelectItem>
          </SelectContent>
        </Select>
        <Select value={userFilter} onValueChange={setUserFilter}>
          <SelectTrigger className="w-[150px]">
            <span className="text-muted-foreground">
              {userFilter === "all" ? "All Users" : userFilter}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Users</SelectItem>
            {uniqueUsers.map((user) => (
              <SelectItem key={user} value={user}>
                {user}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm">
          <CalendarIcon className="size-4" data-icon="inline-start" />
          Date Range
        </Button>
      </div>

      {/* Logs Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Timestamp</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Resource</TableHead>
              <TableHead>Details</TableHead>
              <TableHead>IP Address</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredLogs.map((log) => (
              <TableRow key={log.id}>
                <TableCell>
                  <Typography variant="small">
                    {formatTimestamp(log.timestamp)}
                  </Typography>
                </TableCell>
                <TableCell>
                  <div>
                    <Typography variant="small" className="font-medium">
                      {log.user}
                    </Typography>
                    <Typography variant="muted" className="text-xs">
                      {log.userEmail}
                    </Typography>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={actionConfig[log.action].variant}>
                    {actionConfig[log.action].label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div>
                    <Typography variant="small" className="font-medium">
                      {log.resource}
                    </Typography>
                    <Typography variant="muted" className="text-xs">
                      {log.resourceType}
                    </Typography>
                  </div>
                </TableCell>
                <TableCell>
                  <Typography variant="muted" className="text-sm">
                    {log.details || "-"}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="muted" className="font-mono text-xs">
                    {log.ipAddress}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {filteredLogs.length === 0 && (
        <div className="py-12 text-center">
          <FilterIcon className="text-muted-foreground mx-auto size-12 opacity-50" />
          <Typography variant="h5" className="mt-4">
            No logs found
          </Typography>
          <Typography variant="muted" className="mt-1">
            Try adjusting your filters
          </Typography>
        </div>
      )}
    </div>
  );
}
