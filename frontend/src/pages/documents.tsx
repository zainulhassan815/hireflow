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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { Skeleton } from "@/components/ui/skeleton";
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
import { cn, formatDate, formatFileSize } from "@/lib/utils";
import { toast } from "sonner";

const typeIcons: Record<string, React.ElementType> = {
  resume: FileTextIcon,
  report: FileTextIcon,
  contract: FileIcon,
  letter: FileTextIcon,
  other: ImageIcon,
};

// F90.d — semantic status color: ready → success, processing → warning,
// pending → outline, failed → destructive. Same map as Dashboard.
const statusBadgeClass: Record<string, string> = {
  ready: "bg-success text-success-foreground border-transparent",
  processing: "bg-warning text-warning-foreground border-transparent",
};

const statusVariants: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  ready: "secondary",
  processing: "secondary",
  pending: "outline",
  failed: "destructive",
};

// F90.d — categorical doc-type color. cat-3 deliberately skipped to
// avoid destructive-red collision on rows with a failed status.
const typeBadgeClass: Record<string, string> = {
  resume: "border-cat-1 text-cat-1",
  report: "border-cat-2 text-cat-2",
  contract: "border-cat-5 text-cat-5",
  letter: "border-cat-4 text-cat-4",
};

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [view, setView] = React.useState<"list" | "grid">("list");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [previewDoc, setPreviewDoc] = React.useState<DocumentResponse | null>(
    null
  );
  // F90.f — confirm on delete. Lift state so the AlertDialog renders
  // once at page level rather than per-row.
  const [confirmDelete, setConfirmDelete] =
    React.useState<DocumentResponse | null>(null);

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
    onError: (_, doc) => {
      toast.error(`Couldn't delete ${doc.filename}`, {
        action: {
          label: "Retry",
          onClick: () => deleteMut.mutate(doc),
        },
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
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <Skeleton className="h-8 w-40" />
            <Skeleton className="h-4 w-72" />
          </div>
          <Skeleton className="h-10 w-40" />
        </div>
        <Skeleton className="h-11 w-full max-w-xl" />
        <div className="border">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 border-b p-4">
              <Skeleton className="size-8 shrink-0" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-16" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">Documents</Typography>
          <Typography variant="muted">
            Upload, manage, and search your documents.
          </Typography>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <UploadIcon className="size-4" data-icon="inline-start" />
          Upload Documents
        </Button>
      </div>

      {/* F90.d — search-as-hero. Replaces the old 4-KPI grid. The
          count strip below the search field carries the info the
          grid used to, inline with the filter state. */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[240px] flex-1">
            <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-5 -translate-y-1/2" />
            <Input
              placeholder="Search by filename…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-11 pl-10 text-base"
            />
          </div>
          <div className="flex items-center gap-1">
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
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="tabular-nums">
            {filtered.length === documents.length
              ? `${stats.total} total`
              : `${filtered.length} of ${stats.total}`}
          </span>
          {stats.resumes > 0 && (
            <span className="tabular-nums">· {stats.resumes} resumes</span>
          )}
          {stats.processing > 0 && (
            <span className="text-warning tabular-nums">
              · {stats.processing} processing
            </span>
          )}
          {stats.failed > 0 && (
            <span className="text-destructive tabular-nums">
              · {stats.failed} failed
            </span>
          )}
        </div>
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
                        variant={statusVariants[doc.status] ?? "secondary"}
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
                            onClick={() => setConfirmDelete(doc)}
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
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-xs capitalize",
                          typeBadgeClass[doc.document_type ?? ""]
                        )}
                      >
                        {doc.document_type ?? "—"}
                      </Badge>
                      <Typography
                        variant="muted"
                        className="font-mono text-xs tabular-nums"
                      >
                        {formatFileSize(doc.size_bytes)}
                      </Typography>
                    </div>
                    <Badge
                      variant={statusVariants[doc.status] ?? "secondary"}
                      className={cn(
                        "mt-3 capitalize",
                        statusBadgeClass[doc.status]
                      )}
                    >
                      {doc.status}
                    </Badge>
                    <Typography
                      variant="muted"
                      className="mt-2 text-xs tabular-nums"
                    >
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
      <AlertDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this document?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete?.filename} will be permanently removed. This
              can&rsquo;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (confirmDelete) deleteMut.mutate(confirmDelete);
                setConfirmDelete(null);
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
