import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  DownloadIcon,
  FileTextIcon,
  LayersIcon,
  Loader2Icon,
} from "lucide-react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  downloadDocument,
  getDocumentMetadataOptions,
  getDocumentOptions,
} from "@/api";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
 * Option 3 layout (F108.b): main-area tabs (Document | Text) let the
 * viewer and extracted text compete for the wide column fairly.
 * Right rail holds static Details + a collapsible Similar documents
 * accordion. `keepMounted` on the tab panels preserves viewer state
 * (signed URL, scroll, zoom) across tab switches, and
 * scrollbar-gutter: stable on the scroll containers kills the
 * layout shift when scrollbar visibility changes.
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
    // h-full fills <main>'s content area. flex-col + flex-1 on the
    // body grid lets the viewer + rail grow to the viewport without
    // the outer main scrolling.
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

      {/* grid-rows-[1fr] is load-bearing — without it the grid's
          default `auto` rows stretch to the aside's intrinsic
          content height (tall when the Similar accordion is
          expanded), which overflows the flex-1 min-h-0 container
          and makes <main> scroll the whole page. With 1fr the row
          is clamped to the remaining flex height, so the aside's
          overflow-y-auto scrolls internally and the viewer stays
          pinned. */}
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[1fr] gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        {/* Main column: Document | Text tabs. keepMounted keeps the
            viewer iframe alive when the user peeks at Text, so
            returning to Document doesn't re-fetch the signed URL or
            lose scroll/zoom state. */}
        <Tabs defaultValue="document" className="flex min-h-0 flex-col gap-3">
          <TabsList variant="line" className="self-start">
            <TabsTrigger value="document">Document</TabsTrigger>
            <TabsTrigger value="text">Text</TabsTrigger>
          </TabsList>

          <TabsContent
            value="document"
            keepMounted
            className="flex min-h-0 flex-1 flex-col data-hidden:hidden"
          >
            <DocumentViewer
              documentId={doc.id}
              downloadFallback={() => downloadMutation.mutate()}
            />
          </TabsContent>

          <TabsContent
            value="text"
            keepMounted
            className="min-h-0 flex-1 overflow-y-auto rounded-lg border p-4 [scrollbar-gutter:stable] data-hidden:hidden"
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
        </Tabs>

        {/* Sidebar: always-visible Details + collapsible Similar
            accordion. One scroll container for the whole rail. */}
        <aside className="flex min-h-0 flex-col gap-6 overflow-y-auto pr-1 [scrollbar-gutter:stable]">
          <section aria-labelledby="details-heading">
            <Typography
              variant="muted"
              id="details-heading"
              className="mb-3 text-xs font-medium tracking-wide uppercase"
            >
              Details
            </Typography>
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
          </section>

          <Accordion>
            <AccordionItem value="similar">
              <AccordionTrigger>
                <span className="inline-flex items-center gap-2">
                  <LayersIcon className="text-muted-foreground size-4" />
                  Similar documents
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <SimilarDocuments
                  document={doc}
                  enabled
                  hideHeading
                  onSelect={(neighbourId) =>
                    navigate(`/documents/${neighbourId}`)
                  }
                />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </aside>
      </div>
    </div>
  );
}
