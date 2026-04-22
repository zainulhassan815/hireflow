import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  DownloadIcon,
  FileTextIcon,
  Loader2Icon,
} from "lucide-react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  downloadDocument,
  getDocumentMetadataOptions,
  getDocumentOptions,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Typography } from "@/components/ui/typography";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { SimilarDocuments } from "@/components/documents/similar-documents";
import {
  cn,
  formatDateTime,
  formatFileSize,
  skillHueClass,
  typeBadgeClass,
  typeIconClass,
} from "@/lib/utils";

/**
 * F105.e — focused document page at `/documents/:id`.
 *
 * Full-viewport reading surface: header bar on top (back, tinted
 * glyph, title, download), viewer fills the main column, metadata
 * + text + similar documents live in a tabbed right rail. Replaces
 * the old preview Dialog entirely — list row-click and grid card-
 * click both navigate here.
 */
export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: doc,
    isLoading,
    isError,
  } = useQuery({
    ...getDocumentOptions({ path: { document_id: id ?? "" } }),
    enabled: Boolean(id),
  });

  const { data: metadata } = useQuery({
    ...getDocumentMetadataOptions({ path: { document_id: id ?? "" } }),
    enabled: Boolean(id && doc?.status === "ready"),
  });

  const downloadMutation = useMutation({
    mutationFn: async () => {
      if (!doc) return;
      const { data, error } = await downloadDocument({
        path: { document_id: doc.id },
      });
      if (error) {
        toast.error("Download failed");
        return;
      }
      if (data instanceof Blob) {
        const url = URL.createObjectURL(data);
        const a = Object.assign(document.createElement("a"), {
          href: url,
          download: doc.filename,
        });
        a.click();
        URL.revokeObjectURL(url);
      }
    },
  });

  if (!id) {
    navigate("/documents", { replace: true });
    return null;
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2Icon className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  if (isError || !doc) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <Typography variant="h4">Document not found</Typography>
        <Typography variant="muted">
          It may have been deleted, or you don&apos;t have access.
        </Typography>
        <Button variant="outline" render={<Link to="/documents" />}>
          <ArrowLeftIcon className="size-4" data-icon="inline-start" />
          Back to documents
        </Button>
      </div>
    );
  }

  const meta = metadata?.metadata_ as Record<string, unknown> | null;
  const skills: string[] = Array.isArray(meta?.skills) ? meta.skills : [];
  const docType = doc.document_type ?? "";
  const statusVariant: "default" | "secondary" | "destructive" | "outline" =
    doc.status === "failed"
      ? "destructive"
      : doc.status === "pending"
        ? "outline"
        : "secondary";
  const statusClass: string | undefined =
    doc.status === "ready"
      ? "bg-success text-success-foreground border-transparent"
      : doc.status === "processing"
        ? "bg-warning text-warning-foreground border-transparent"
        : undefined;

  return (
    // h-full fills <main>'s content area (app-layout.tsx gives <main>
    // flex-1 inside SidebarInset). flex-col + flex-1 on the body
    // lets the viewer + rail grow to the viewport without the outer
    // main scrolling.
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center gap-3 border-b pb-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/documents")}
          aria-label="Back to documents"
        >
          <ArrowLeftIcon className="size-4" />
        </Button>
        <div
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded",
            typeIconClass[docType] ?? "bg-muted text-muted-foreground"
          )}
        >
          <FileTextIcon className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <Typography
            variant="h5"
            className="truncate text-base font-semibold tracking-tight"
          >
            {doc.filename}
          </Typography>
          <Typography
            variant="muted"
            className="font-mono text-xs tabular-nums"
          >
            {formatFileSize(doc.size_bytes)} &middot;{" "}
            {formatDateTime(doc.created_at)}
          </Typography>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => downloadMutation.mutate()}
          disabled={downloadMutation.isPending}
        >
          <DownloadIcon className="size-4" data-icon="inline-start" />
          Download
        </Button>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="bg-muted/20 flex min-h-0 flex-col rounded-lg border p-3">
          <DocumentViewer
            documentId={doc.id}
            downloadFallback={() => downloadMutation.mutate()}
          />
        </div>

        <Tabs
          defaultValue="details"
          className="flex min-h-0 flex-col gap-0 rounded-lg border"
        >
          <TabsList className="bg-background shrink-0 justify-start rounded-none rounded-t-lg border-b px-3">
            <TabsTrigger value="details">Details</TabsTrigger>
            <TabsTrigger value="text">Text</TabsTrigger>
            <TabsTrigger value="similar">Similar</TabsTrigger>
          </TabsList>

          <TabsContent
            value="details"
            className="min-h-0 flex-1 overflow-auto px-4 py-4"
          >
            <dl className="flex flex-col gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground mb-1 text-xs tracking-wide uppercase">
                  Type
                </dt>
                <dd>
                  <Badge
                    variant="outline"
                    className={cn("capitalize", typeBadgeClass[docType])}
                  >
                    {docType || "unclassified"}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground mb-1 text-xs tracking-wide uppercase">
                  Status
                </dt>
                <dd>
                  <Badge
                    variant={statusVariant}
                    className={cn("capitalize", statusClass)}
                  >
                    {doc.status}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground mb-1 text-xs tracking-wide uppercase">
                  Size
                </dt>
                <dd className="font-mono tabular-nums">
                  {formatFileSize(doc.size_bytes)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground mb-1 text-xs tracking-wide uppercase">
                  Uploaded
                </dt>
                <dd className="tabular-nums">
                  {formatDateTime(doc.created_at)}
                </dd>
              </div>
              {skills.length > 0 && (
                <div>
                  <dt className="text-muted-foreground mb-1 text-xs tracking-wide uppercase">
                    Skills
                  </dt>
                  <dd className="flex flex-wrap gap-1">
                    {skills.map((s) => (
                      <Badge
                        key={s}
                        variant="outline"
                        className={cn("text-xs", skillHueClass(s))}
                      >
                        {s}
                      </Badge>
                    ))}
                  </dd>
                </div>
              )}
            </dl>
          </TabsContent>

          <TabsContent
            value="text"
            className="min-h-0 flex-1 overflow-auto px-4 py-4"
          >
            {metadata?.extracted_text ? (
              <div className="text-foreground/90 font-mono text-xs leading-relaxed whitespace-pre-wrap">
                {metadata.extracted_text}
              </div>
            ) : doc.status === "processing" || doc.status === "pending" ? (
              <div className="bg-muted/40 flex h-full min-h-[8rem] items-center justify-center rounded-lg p-6 text-center">
                <Typography variant="muted">
                  Document is still being processed.
                </Typography>
              </div>
            ) : (
              <div className="bg-muted/40 flex h-full min-h-[8rem] items-center justify-center rounded-lg p-6 text-center">
                <Typography variant="muted">
                  No extracted text available.
                </Typography>
              </div>
            )}
          </TabsContent>

          <TabsContent
            value="similar"
            className="min-h-0 flex-1 overflow-auto px-4 py-4"
          >
            <SimilarDocuments
              document={doc}
              enabled
              onSelect={(neighbourId) => navigate(`/documents/${neighbourId}`)}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
