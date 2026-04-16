import * as React from "react";
import { useNavigate } from "react-router-dom";
import {
  BriefcaseIcon,
  FileTextIcon,
  CheckCircleIcon,
  UploadIcon,
  UsersIcon,
  SearchIcon,
} from "lucide-react";

import {
  candidatesListCandidates,
  documentsListDocuments,
  jobsListJobs,
  type CandidateResponse,
  type DocumentResponse,
  type JobResponse,
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
import { formatDate, formatFileSize } from "@/lib/utils";
import { useAuth } from "@/providers/use-auth";

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [documents, setDocuments] = React.useState<DocumentResponse[]>([]);
  const [jobs, setJobs] = React.useState<JobResponse[]>([]);
  const [candidates, setCandidates] = React.useState<CandidateResponse[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([
      documentsListDocuments(),
      jobsListJobs(),
      candidatesListCandidates(),
    ]).then(([docRes, jobRes, candRes]) => {
      setDocuments(docRes.data ?? []);
      setJobs(jobRes.data ?? []);
      setCandidates(candRes.data ?? []);
      setLoading(false);
    });
  }, []);

  const stats = {
    documents: documents.length,
    jobs: jobs.length,
    candidates: candidates.length,
    openJobs: jobs.filter((j) => j.status === "open").length,
    processed: documents.filter((d) => d.status === "ready").length,
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
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">
            Welcome back{user?.full_name ? `, ${user.full_name}` : ""}
          </Typography>
          <Typography variant="muted">
            Here&rsquo;s an overview of your document library
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

      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Documents
              </Typography>
              <FileTextIcon className="text-muted-foreground size-4" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.documents}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Jobs
              </Typography>
              <BriefcaseIcon className="text-muted-foreground size-4" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.jobs}
            </Typography>
            <Typography variant="muted" className="text-xs">
              {stats.openJobs} open
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Candidates
              </Typography>
              <UsersIcon className="text-muted-foreground size-4" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.candidates}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Processed
              </Typography>
              <CheckCircleIcon className="size-4 text-green-500" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.processed}
            </Typography>
          </CardContent>
        </Card>
      </div>

      {/* Recent Documents */}
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
                      <Badge variant="outline" className="capitalize">
                        {doc.document_type ?? "—"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography variant="small">
                        {formatFileSize(doc.size_bytes)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          doc.status === "ready"
                            ? "default"
                            : doc.status === "failed"
                              ? "destructive"
                              : "secondary"
                        }
                        className="capitalize"
                      >
                        {doc.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography variant="muted">
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
