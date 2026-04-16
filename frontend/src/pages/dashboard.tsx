import * as React from "react";
import { useNavigate } from "react-router-dom";
import {
  FileTextIcon,
  CheckCircleIcon,
  ClockIcon,
  AlertCircleIcon,
  UploadIcon,
  SearchIcon,
} from "lucide-react";

import { documentsListDocuments, type DocumentResponse } from "@/api";
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
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    documentsListDocuments().then(({ data }) => {
      setDocuments(data ?? []);
      setLoading(false);
    });
  }, []);

  const stats = {
    total: documents.length,
    ready: documents.filter((d) => d.status === "ready").length,
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
                Total Documents
              </Typography>
              <FileTextIcon className="text-muted-foreground size-4" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.total}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Ready
              </Typography>
              <CheckCircleIcon className="size-4 text-green-500" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.ready}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Processing
              </Typography>
              <ClockIcon className="size-4 text-yellow-500" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.processing}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <Typography variant="muted" className="text-xs">
                Failed
              </Typography>
              <AlertCircleIcon className="size-4 text-red-500" />
            </div>
            <Typography variant="h3" className="mt-2">
              {stats.failed}
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
