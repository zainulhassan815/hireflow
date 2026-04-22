import * as React from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  CloudUploadIcon,
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
  XIcon,
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
import { Checkbox } from "@/components/ui/checkbox";
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
import { uploadFiles } from "@/lib/upload-documents";
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

// Tinted icon container mirroring the badge taxonomy. 10%-alpha
// background pairs with solid-hue glyph so the eye lands on a
// colored surface first, not on gray.
const typeIconClass: Record<string, string> = {
  resume: "bg-cat-1/10 text-cat-1",
  report: "bg-cat-2/10 text-cat-2",
  contract: "bg-cat-5/10 text-cat-5",
  letter: "bg-cat-4/10 text-cat-4",
};

export function DocumentsPage() {
  const queryClient = useQueryClient();
  const [view, setView] = React.useState<"list" | "grid">("list");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [previewDoc, setPreviewDoc] = React.useState<DocumentResponse | null>(
    null
  );
  const [confirmDelete, setConfirmDelete] =
    React.useState<DocumentResponse | null>(null);
  // F91 — page-level drag-and-drop. Track drag depth so the overlay
  // doesn't flicker when dragging over nested children.
  const [isDragging, setIsDragging] = React.useState(false);
  const dragDepth = React.useRef(0);
  // F91 — bulk selection. Set of doc IDs; cleared on filter change.
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(
    () => new Set()
  );
  const [bulkConfirmOpen, setBulkConfirmOpen] = React.useState(false);

  const invalidateDocs = React.useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: listDocumentsOptions().queryKey,
    });
  }, [queryClient]);

  const { data: documents = [], isLoading } = useQuery({
    ...listDocumentsOptions(),
    select: (data) => data ?? [],
    // F91 — live status polling. While any doc is pending/processing,
    // refetch every 3s so the table updates without a manual refresh.
    refetchInterval: (q) => {
      const docs = (q.state.data as DocumentResponse[] | undefined) ?? [];
      const anyProcessing = docs.some(
        (d) => d.status === "pending" || d.status === "processing"
      );
      return anyProcessing ? 3000 : false;
    },
  });

  const deleteMut = useMutation({
    mutationFn: (doc: DocumentResponse) =>
      deleteDocument({ path: { document_id: doc.id } }),
    onSuccess: (_, doc) => {
      toast.success(`${doc.filename} deleted`);
      invalidateDocs();
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
    invalidateDocs();
  };

  const handleDropUpload = React.useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      const id = toast.loading(
        files.length === 1
          ? `Uploading ${files[0].name}…`
          : `Uploading ${files.length} files…`
      );
      const { succeeded, failed } = await uploadFiles(files);
      toast.dismiss(id);
      if (succeeded.length > 0) {
        toast.success(
          succeeded.length === 1
            ? `${succeeded[0].filename} uploaded`
            : `${succeeded.length} files uploaded`
        );
        invalidateDocs();
      }
      if (failed.length > 0 && succeeded.length === 0) {
        // Per-file error toasts already fired inside uploadFiles; no
        // extra summary needed.
      }
    },
    [invalidateDocs]
  );

  const onDragEnter = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepth.current += 1;
    setIsDragging(true);
  };

  const onDragOver = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
  };

  const onDragLeave = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);
    void handleDropUpload(Array.from(e.dataTransfer.files));
  };

  const filtered = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // F91 — keep selection coherent with current filter + deletions.
  React.useEffect(() => {
    setSelectedIds((prev) => {
      const visibleIds = new Set(filtered.map((d) => d.id));
      let changed = false;
      const next = new Set<string>();
      prev.forEach((id) => {
        if (visibleIds.has(id)) next.add(id);
        else changed = true;
      });
      return changed ? next : prev;
    });
  }, [filtered]);

  const allSelected =
    filtered.length > 0 && filtered.every((d) => selectedIds.has(d.id));
  const someSelected = selectedIds.size > 0 && !allSelected;

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (prev.size > 0) return new Set();
      return new Set(filtered.map((d) => d.id));
    });
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const runBulkDelete = async () => {
    const targets = documents.filter((d) => selectedIds.has(d.id));
    setBulkConfirmOpen(false);
    setSelectedIds(new Set());
    const results = await Promise.allSettled(
      targets.map((d) => deleteDocument({ path: { document_id: d.id } }))
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.length - ok;
    if (ok > 0) toast.success(`${ok} document${ok === 1 ? "" : "s"} deleted`);
    if (failed > 0)
      toast.error(`${failed} couldn't be deleted. Refresh to retry.`);
    invalidateDocs();
  };

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
    <div
      className="relative flex flex-col gap-8"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {isDragging && (
        <div className="bg-foreground/60 pointer-events-none fixed inset-0 z-40 flex items-center justify-center backdrop-blur-sm">
          <div className="bg-background border-primary flex flex-col items-center gap-3 border-2 border-dashed px-10 py-8">
            <CloudUploadIcon className="text-primary size-10" />
            <Typography variant="h5">Drop to upload</Typography>
            <Typography variant="muted" className="text-sm">
              PDF, DOC, DOCX, PNG, JPG, TIFF — up to 10MB each.
            </Typography>
          </div>
        </div>
      )}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Typography variant="h3">Documents</Typography>
          <Typography variant="muted">
            Upload, manage, and search your documents. Drag files anywhere to
            upload.
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
          <div className="bg-primary/10 flex size-16 items-center justify-center rounded">
            <FileTextIcon className="text-primary size-8" />
          </div>
          <Typography variant="h4" className="mt-4 max-w-[28ch]">
            Nothing here yet.
          </Typography>
          <Typography variant="muted" className="mt-1 max-w-[48ch]">
            Upload resumes, reports, contracts — whatever you want to search
            later. They&rsquo;ll show up as soon as processing finishes.
          </Typography>
          <Button className="mt-4" onClick={() => setUploadOpen(true)}>
            <UploadIcon className="size-4" data-icon="inline-start" />
            Upload Documents
          </Button>
        </div>
      ) : view === "list" ? (
        <>
          {selectedIds.size > 0 && (
            <div className="bg-muted/50 flex items-center justify-between border px-4 py-2">
              <Typography variant="small" className="tabular-nums">
                {selectedIds.size} selected
              </Typography>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedIds(new Set())}
                >
                  <XIcon className="size-4" data-icon="inline-start" />
                  Clear
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setBulkConfirmOpen(true)}
                >
                  <TrashIcon className="size-4" data-icon="inline-start" />
                  Delete
                </Button>
              </div>
            </div>
          )}
          <div className="border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={allSelected}
                      indeterminate={someSelected}
                      onCheckedChange={() => toggleSelectAll()}
                      aria-label="Select all rows"
                    />
                  </TableHead>
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
                  const isSelected = selectedIds.has(doc.id);
                  return (
                    <TableRow
                      key={doc.id}
                      data-state={isSelected ? "selected" : undefined}
                    >
                      <TableCell>
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => toggleSelect(doc.id)}
                          aria-label={`Select ${doc.filename}`}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div
                            className={cn(
                              "flex size-8 items-center justify-center rounded",
                              typeIconClass[doc.document_type ?? ""] ??
                                "bg-muted text-muted-foreground"
                            )}
                          >
                            <TypeIcon className="size-4" />
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
                          <DropdownMenuTrigger
                            render={
                              <Button variant="ghost" size="icon-sm">
                                <MoreHorizontalIcon className="size-4" />
                              </Button>
                            }
                          />
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => setPreviewDoc(doc)}
                            >
                              <EyeIcon className="mr-2 size-4" />
                              Preview
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => handleDownload(doc)}
                            >
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
        </>
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
                  <div
                    className={cn(
                      "flex size-12 items-center justify-center rounded",
                      typeIconClass[doc.document_type ?? ""] ??
                        "bg-muted text-muted-foreground"
                    )}
                  >
                    <TypeIcon className="size-6" />
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
      <AlertDialog open={bulkConfirmOpen} onOpenChange={setBulkConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete {selectedIds.size} document
              {selectedIds.size === 1 ? "" : "s"}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove the selected documents. It
              can&rsquo;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={runBulkDelete}
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
