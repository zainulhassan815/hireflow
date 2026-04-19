import * as React from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  DownloadIcon,
  EyeIcon,
  FileIcon,
  FileTextIcon,
  GridIcon,
  ImageIcon,
  ListIcon,
  MoreHorizontalIcon,
  SearchIcon,
  TrashIcon,
  UploadIcon,
} from "lucide-react";

import {
  listDocumentsOptions,
  deleteDocument,
  downloadDocument,
  type DocumentResponse,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { UploadDialog } from "@/components/documents/upload-dialog";
import { DocumentPreview } from "@/components/documents/document-preview";
import { formatDate, formatFileSize } from "@/lib/utils";
import { toast } from "sonner";

const typeIcons: Record<string, React.ElementType> = {
  resume: FileTextIcon,
  report: FileTextIcon,
  contract: FileIcon,
  letter: FileTextIcon,
  other: ImageIcon,
};

const statusVariants: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  ready: "default",
  processing: "secondary",
  pending: "outline",
  failed: "destructive",
};

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [view, setView] = React.useState<"list" | "grid">("list");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [previewDoc, setPreviewDoc] = React.useState<DocumentResponse | null>(
    null
  );

  const { data: documents = [], isLoading } = useQuery({
    ...listDocumentsOptions(),
    select: (data) => data ?? [],
  });

  const deleteMut = useMutation({
    mutationFn: (doc: DocumentResponse) =>
      deleteDocument({ path: { document_id: doc.id } }),
    onSuccess: (_, doc) => {
      toast.success(`${doc.filename} deleted`);
      queryClient.invalidateQueries({
        queryKey: listDocumentsOptions().queryKey,
      });
    },
  });

  const handleDownload = async (doc: DocumentResponse) => {
    const { data, error } = await downloadDocument({
      path: { document_id: doc.id },
    });
    if (error) {
      toast.error("Download failed");
      return;
    }
    if (data instanceof Blob) {
      const url = URL.createObjectURL(data);
      const a = Object.assign(window.document.createElement("a"), {
        href: url,
        download: doc.filename,
      });
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const handleUploaded = () => {
    queryClient.invalidateQueries({
      queryKey: listDocumentsOptions().queryKey,
    });
  };

  const filtered = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const stats = {
    total: documents.length,
    resumes: documents.filter((d) => d.document_type === "resume").length,
    processing: documents.filter(
      (d) => d.status === "processing" || d.status === "pending"
    ).length,
    failed: documents.filter((d) => d.status === "failed").length,
  };

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
          <Typography variant="h3">Documents</Typography>
          <Typography variant="muted">
            Upload, manage, and search your documents
          </Typography>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <UploadIcon className="size-4" data-icon="inline-start" />
          Upload Documents
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="relative max-w-sm min-w-[200px] flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant={view === "list" ? "secondary" : "ghost"}
            size="icon-sm"
            onClick={() => setView("list")}
          >
            <ListIcon className="size-4" />
          </Button>
          <Button
            variant={view === "grid" ? "secondary" : "ghost"}
            size="icon-sm"
            onClick={() => setView("grid")}
          >
            <GridIcon className="size-4" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(
          [
            ["Total", stats.total],
            ["Resumes", stats.resumes],
            ["Processing", stats.processing],
            ["Failed", stats.failed],
          ] as const
        ).map(([label, count]) => (
          <Card key={label}>
            <CardContent className="p-4">
              <Typography variant="muted" className="text-xs">
                {label}
              </Typography>
              <Typography variant="h4" className="mt-1">
                {count}
              </Typography>
            </CardContent>
          </Card>
        ))}
      </div>

      {documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <FileTextIcon className="text-muted-foreground size-12" />
          <Typography variant="h4" className="mt-4">
            No documents yet
          </Typography>
          <Typography variant="muted" className="mt-1">
            Upload your first document to get started
          </Typography>
          <Button className="mt-4" onClick={() => setUploadOpen(true)}>
            <UploadIcon className="size-4" data-icon="inline-start" />
            Upload Documents
          </Button>
        </div>
      ) : view === "list" ? (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((doc) => {
                const TypeIcon =
                  typeIcons[doc.document_type ?? "other"] ?? FileIcon;
                return (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="bg-muted flex size-8 items-center justify-center rounded">
                          <TypeIcon className="text-muted-foreground size-4" />
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
                      <Typography
                        variant="small"
                        className="font-mono tabular-nums"
                      >
                        {formatFileSize(doc.size_bytes)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={statusVariants[doc.status] ?? "secondary"}
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
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm">
                            <MoreHorizontalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => setPreviewDoc(doc)}>
                            <EyeIcon className="mr-2 size-4" />
                            Preview
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleDownload(doc)}>
                            <DownloadIcon className="mr-2 size-4" />
                            Download
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => deleteMut.mutate(doc)}
                          >
                            <TrashIcon className="mr-2 size-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((doc) => {
            const TypeIcon =
              typeIcons[doc.document_type ?? "other"] ?? FileIcon;
            return (
              <Card
                key={doc.id}
                className="cursor-pointer transition-shadow hover:shadow-md"
                onClick={() => setPreviewDoc(doc)}
              >
                <CardContent className="p-4">
                  <div className="bg-muted flex size-12 items-center justify-center rounded">
                    <TypeIcon className="text-muted-foreground size-6" />
                  </div>
                  <div className="mt-4">
                    <Typography
                      variant="small"
                      className="line-clamp-1 font-medium"
                    >
                      {doc.filename}
                    </Typography>
                    <div className="mt-2 flex items-center gap-2">
                      <Badge variant="outline" className="text-xs capitalize">
                        {doc.document_type ?? "—"}
                      </Badge>
                      <Typography variant="muted" className="text-xs">
                        {formatFileSize(doc.size_bytes)}
                      </Typography>
                    </div>
                    <Badge
                      variant={statusVariants[doc.status] ?? "secondary"}
                      className="mt-3 capitalize"
                    >
                      {doc.status}
                    </Badge>
                    <Typography variant="muted" className="mt-2 text-xs">
                      {formatDate(doc.created_at)}
                    </Typography>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={handleUploaded}
      />
      <DocumentPreview
        document={previewDoc}
        open={!!previewDoc}
        onOpenChange={(open) => !open && setPreviewDoc(null)}
      />
    </div>
  );
}
