import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileTextIcon, UploadIcon, SearchIcon } from "lucide-react";

import {
  listDocumentsOptions,
  listJobsOptions,
  listCandidatesOptions,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { cn, formatDate, formatFileSize } from "@/lib/utils";
import { useAuth } from "@/providers/use-auth";

// F90.d — semantic status badge color map (ready/processing).
// pending stays on outline variant; failed stays on destructive.
const statusBadgeClass: Record<string, string> = {
  ready: "bg-success text-success-foreground border-transparent",
  processing: "bg-warning text-warning-foreground border-transparent",
};

// F90.d — categorical doc-type color map. resume → cat-1 (primary
// category), report → cat-2, contract → cat-5 (avoid cat-3 to dodge
// destructive-red collision), letter → cat-4.
const typeBadgeClass: Record<string, string> = {
  resume: "border-cat-1 text-cat-1",
  report: "border-cat-2 text-cat-2",
  contract: "border-cat-5 text-cat-5",
  letter: "border-cat-4 text-cat-4",
};

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: documents = [], isLoading: docsLoading } = useQuery({
    ...listDocumentsOptions(),
    select: (data) => data ?? [],
  });
  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    ...listJobsOptions(),
    select: (data) => data ?? [],
  });
  const { data: candidates = [], isLoading: candsLoading } = useQuery({
    ...listCandidatesOptions(),
    select: (data) => data ?? [],
  });

  const loading = docsLoading || jobsLoading || candsLoading;

  const stats = {
    documents: documents.length,
    jobs: jobs.length,
    candidates: candidates.length,
    openJobs: jobs.filter((j) => j.status === "open").length,
    processed: documents.filter((d) => d.status === "ready").length,
    processing: documents.filter(
      (d) => d.status === "processing" || d.status === "pending"
    ).length,
    failed: documents.filter((d) => d.status === "failed").length,
  };

  const recent = documents.slice(0, 5);

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Spinner className="size-8" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">
            Welcome back{user?.full_name ? `, ${user.full_name}` : ""}
          </Typography>
          <Typography variant="muted">
            Here&rsquo;s the state of your library today.
          </Typography>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate("/search")}>
            <SearchIcon className="size-4" data-icon="inline-start" />
            Search
          </Button>
          <Button onClick={() => navigate("/documents")}>
            <UploadIcon className="size-4" data-icon="inline-start" />
            Upload
          </Button>
        </div>
      </div>

      {/* F90.d — hero: document processing state as the headline
          metric. Big display number, ratio context, right-rail stat
          strip for the secondary dimensions (jobs / candidates). */}
      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(200px,auto)]">
        <div className="flex flex-col gap-3">
          <Typography
            variant="muted"
            className="text-xs tracking-[0.1em] uppercase"
          >
            Library
          </Typography>
          <div className="flex items-baseline gap-3">
            <span className="font-display text-6xl font-semibold tracking-[-0.02em] tabular-nums">
              {stats.processed}
            </span>
            <Typography variant="muted" className="tabular-nums">
              of {stats.documents} ready
            </Typography>
          </div>
          {stats.processing > 0 || stats.failed > 0 ? (
            <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              {stats.processing > 0 && (
                <span className="text-warning tabular-nums">
                  {stats.processing} processing
                </span>
              )}
              {stats.failed > 0 && (
                <span className="text-destructive tabular-nums">
                  {stats.failed} failed
                </span>
              )}
            </div>
          ) : (
            stats.documents > 0 && (
              <Typography variant="muted" className="text-sm">
                All documents processed.
              </Typography>
            )
          )}
        </div>
        <div className="text-muted-foreground flex flex-row gap-6 md:flex-col md:items-end md:gap-3 md:text-right">
          <div>
            <Typography
              variant="muted"
              className="text-xs tracking-[0.1em] uppercase"
            >
              Jobs
            </Typography>
            <div className="text-foreground mt-1 text-2xl font-semibold tabular-nums">
              {stats.jobs}
            </div>
            <Typography variant="muted" className="text-xs tabular-nums">
              {stats.openJobs} open
            </Typography>
          </div>
          <div>
            <Typography
              variant="muted"
              className="text-xs tracking-[0.1em] uppercase"
            >
              Candidates
            </Typography>
            <div className="text-foreground mt-1 text-2xl font-semibold tabular-nums">
              {stats.candidates}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <Typography variant="h5">Recent Documents</Typography>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => navigate("/documents")}
          >
            View All
          </Button>
        </div>

        {recent.length === 0 ? (
          <Card className="border">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <FileTextIcon className="text-muted-foreground size-12" />
              <Typography variant="h5" className="mt-4">
                No documents yet
              </Typography>
              <Typography variant="muted" className="mt-1">
                Upload your first document to get started
              </Typography>
              <Button className="mt-4" onClick={() => navigate("/documents")}>
                <UploadIcon className="size-4" data-icon="inline-start" />
                Go to Documents
              </Button>
            </CardContent>
          </Card>
        ) : (
          <Card className="border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Uploaded</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((doc) => (
                  <TableRow
                    key={doc.id}
                    className="cursor-pointer"
                    onClick={() => navigate("/documents")}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="bg-muted flex size-8 items-center justify-center rounded">
                          <FileTextIcon className="text-muted-foreground size-4" />
                        </div>
                        <Typography variant="small" className="font-medium">
                          {doc.filename}
                        </Typography>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn(
                          "capitalize",
                          typeBadgeClass[doc.document_type ?? ""]
                        )}
                      >
                        {doc.document_type ?? "—"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="small"
                        className="font-mono tabular-nums"
                      >
                        {formatFileSize(doc.size_bytes)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          doc.status === "failed"
                            ? "destructive"
                            : doc.status === "pending"
                              ? "outline"
                              : "secondary"
                        }
                        className={cn(
                          "capitalize",
                          statusBadgeClass[doc.status]
                        )}
                      >
                        {doc.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography variant="muted" className="tabular-nums">
                        {formatDate(doc.created_at)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>
    </div>
  );
}
