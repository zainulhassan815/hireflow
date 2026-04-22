import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, DownloadIcon, Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  downloadDocument,
  getDocumentMetadataOptions,
  getDocumentOptions,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Typography } from "@/components/ui/typography";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { SimilarDocuments } from "@/components/documents/similar-documents";
import { formatDateTime, formatFileSize } from "@/lib/utils";

/**
 * F105.e — focused document page at `/documents/:id`.
 *
 * Same `<DocumentViewer>` as the dialog, but given the whole viewport:
 * viewer occupies the main column with fuller chrome (back button,
 * filename in the header), metadata + similar-docs move to a sticky
 * right sidebar. Pair with the dialog, which stays for quick peeks.
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
      <div className="flex h-[60vh] items-center justify-center">
        <Loader2Icon className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  if (isError || !doc) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/documents")}
          aria-label="Back to documents"
        >
          <ArrowLeftIcon className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <Typography variant="h3" className="truncate">
            {doc.filename}
          </Typography>
          <Typography variant="muted" className="text-sm">
            {formatFileSize(doc.size_bytes)} &middot;{" "}
            {formatDateTime(doc.created_at)}
          </Typography>
        </div>
        <Button
          onClick={() => downloadMutation.mutate()}
          disabled={downloadMutation.isPending}
        >
          <DownloadIcon className="size-4" data-icon="inline-start" />
          Download
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <DocumentViewer
            documentId={doc.id}
            downloadFallback={() => downloadMutation.mutate()}
          />
        </div>

        <aside className="flex flex-col gap-4">
          <div className="rounded-lg border p-4">
            <Typography variant="h6" className="mb-3">
              Details
            </Typography>
            <dl className="grid gap-3 text-sm">
              <div>
                <dt className="text-muted-foreground text-xs">Type</dt>
                <dd className="mt-1">
                  <Badge variant="outline" className="capitalize">
                    {doc.document_type ?? "unclassified"}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Status</dt>
                <dd className="mt-1">
                  <Badge
                    variant={doc.status === "ready" ? "default" : "secondary"}
                    className="capitalize"
                  >
                    {doc.status}
                  </Badge>
                </dd>
              </div>
              {skills.length > 0 && (
                <div>
                  <dt className="text-muted-foreground text-xs">Skills</dt>
                  <dd className="mt-1 flex flex-wrap gap-1">
                    {skills.map((s) => (
                      <Badge key={s} variant="secondary" className="text-xs">
                        {s}
                      </Badge>
                    ))}
                  </dd>
                </div>
              )}
            </dl>
          </div>

          <Separator />

          <div>
            <SimilarDocuments
              document={doc}
              enabled
              onSelect={(neighbourId) => navigate(`/documents/${neighbourId}`)}
            />
          </div>
        </aside>
      </div>
    </div>
  );
}
