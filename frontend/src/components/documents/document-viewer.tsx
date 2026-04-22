import { useQuery } from "@tanstack/react-query";
import { DownloadIcon, FileTextIcon, Loader2Icon } from "lucide-react";

import { getDocumentViewableOptions } from "@/api";
import type { ViewablePayloadResponse } from "@/api";
import { TableRenderer } from "@/components/documents/table-renderer";
import { Typography } from "@/components/ui/typography";

/**
 * F105.a — pure dispatcher.
 *
 * Switches on ``payload.kind`` to pick a renderer. Adding a new
 * kind = adding a branch + a renderer component; existing
 * branches never need to know. Mirrors the backend
 * ``ViewerRegistry``.
 */
export function DocumentViewer({
  documentId,
  downloadFallback,
}: {
  documentId: string;
  downloadFallback?: () => void;
}) {
  const { data, isLoading, isError } = useQuery({
    ...getDocumentViewableOptions({ path: { document_id: documentId } }),
    // The signed URL carries a one-hour expiry. Re-fetching on
    // mount per dialog-open is enough; no interval polling needed.
    staleTime: 30 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="bg-muted/50 flex h-64 items-center justify-center rounded-lg">
        <Loader2Icon className="text-muted-foreground size-5 animate-spin" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="bg-muted/50 rounded-lg p-6 text-center">
        <Typography variant="muted">
          Couldn&apos;t load the viewer. Try downloading the file instead.
        </Typography>
      </div>
    );
  }

  return <PayloadView payload={data} downloadFallback={downloadFallback} />;
}

function PayloadView({
  payload,
  downloadFallback,
}: {
  payload: ViewablePayloadResponse;
  downloadFallback?: () => void;
}) {
  switch (payload.kind) {
    case "pdf":
      return <PdfView url={payload.url ?? ""} />;
    case "image":
      return <ImageView url={payload.url ?? ""} />;
    case "table":
      return <TableRenderer data={payload.data} />;
    case "text":
      // F105.d ships a real renderer for text. Until then,
      // the fallback view is honest about it — no fake "coming soon"
      // chrome, just the download affordance.
      return (
        <UnsupportedView
          reason="no_viewer_for_mime"
          meta={payload.meta}
          downloadFallback={downloadFallback}
        />
      );
    case "unsupported":
    default:
      return (
        <UnsupportedView
          reason={(payload.meta?.reason as string) ?? "no_viewer_for_mime"}
          meta={payload.meta}
          downloadFallback={downloadFallback}
        />
      );
  }
}

function PdfView({ url }: { url: string }) {
  return (
    <iframe
      src={url}
      title="Document preview"
      className="h-[600px] w-full rounded-lg border bg-white"
    />
  );
}

function ImageView({ url }: { url: string }) {
  return (
    <div className="bg-muted/30 flex max-h-[600px] items-center justify-center overflow-auto rounded-lg border">
      <img
        src={url}
        alt="Document preview"
        className="max-h-[600px] max-w-full object-contain"
      />
    </div>
  );
}

function UnsupportedView({
  reason,
  meta,
  downloadFallback,
}: {
  reason: string;
  meta: Record<string, unknown> | null | undefined;
  downloadFallback?: () => void;
}) {
  const message =
    reason === "not_ready"
      ? "Document is still being processed."
      : "Inline preview isn't available for this file type.";

  const filename = typeof meta?.filename === "string" ? meta.filename : null;

  return (
    <div className="bg-muted/40 flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-8 text-center">
      <FileTextIcon className="text-muted-foreground size-8" />
      <Typography variant="small" className="font-medium">
        {message}
      </Typography>
      {filename ? (
        <Typography variant="muted" className="text-xs">
          {filename}
        </Typography>
      ) : null}
      {downloadFallback && reason !== "not_ready" ? (
        <button
          type="button"
          onClick={downloadFallback}
          className="text-primary inline-flex items-center gap-1 text-sm hover:underline"
        >
          <DownloadIcon className="size-3.5" />
          Download to view
        </button>
      ) : null}
    </div>
  );
}
