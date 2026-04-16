import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardListIcon, RefreshCwIcon, SearchIcon } from "lucide-react";

import { listLogsOptions } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Typography } from "@/components/ui/typography";
import { formatDateTime } from "@/lib/utils";

const actionVariant: Record<
  string,
  "default" | "secondary" | "outline" | "destructive"
> = {
  login: "default",
  logout: "outline",
  register: "default",
  document_upload: "secondary",
  document_delete: "destructive",
  document_processed: "secondary",
  job_create: "default",
  job_update: "secondary",
  job_delete: "destructive",
  candidate_create: "default",
  candidate_match: "secondary",
  application_status_change: "outline",
  password_reset: "outline",
};

export function LogsPage() {
  const [searchQuery, setSearchQuery] = React.useState("");

  const {
    data: logs = [],
    isLoading,
    refetch,
  } = useQuery({
    ...listLogsOptions({ query: { limit: 100 } }),
    select: (data) => data ?? [],
  });

  const filtered = logs.filter((log) => {
    const q = searchQuery.toLowerCase();
    return (
      log.action.toLowerCase().includes(q) ||
      (log.detail ?? "").toLowerCase().includes(q) ||
      (log.resource_type ?? "").toLowerCase().includes(q)
    );
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Spinner className="size-8" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">Activity Logs</Typography>
          <Typography variant="muted">
            Audit trail of actions in the system
          </Typography>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCwIcon className="size-4" data-icon="inline-start" />
          Refresh
        </Button>
      </div>

      <div className="relative max-w-sm min-w-[200px]">
        <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          placeholder="Search by action, detail, or resource..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      {logs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <ClipboardListIcon className="text-muted-foreground size-12" />
          <Typography variant="h4" className="mt-4">
            No activity yet
          </Typography>
          <Typography variant="muted" className="mt-1">
            Actions like login, uploads, and job operations will appear here
          </Typography>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((log) => (
                <TableRow key={log.id}>
                  <TableCell>
                    <Badge
                      variant={actionVariant[log.action] ?? "outline"}
                      className="text-xs"
                    >
                      {log.action.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Typography variant="small">
                      {log.resource_type
                        ? `${log.resource_type}${log.resource_id ? ` / ${log.resource_id.slice(0, 8)}...` : ""}`
                        : "—"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="muted" className="max-w-xs truncate">
                      {log.detail || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="muted" className="text-xs">
                      {log.ip_address || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="muted" className="text-xs">
                      {formatDateTime(log.created_at)}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
