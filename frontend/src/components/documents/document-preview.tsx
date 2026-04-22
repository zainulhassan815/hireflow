import { DownloadIcon, FileTextIcon, XIcon } from "lucide-react";

import {
  downloadDocument,
  getDocument,
  getDocumentMetadata,
  listDocumentsOptions,
  type DocumentResponse,
  type DocumentMetadataResponse,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Typography } from "@/components/ui/typography";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { SimilarDocuments } from "@/components/documents/similar-documents";
import { cn, formatDateTime, formatFileSize, skillHueClass } from "@/lib/utils";
import { toast } from "sonner";
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";

interface DocumentPreviewProps {
  document: DocumentResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentPreview({
  document: doc,
  open,
  onOpenChange,
}: DocumentPreviewProps) {
  const queryClient = useQueryClient();
  const [metadata, setMetadata] =
    React.useState<DocumentMetadataResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  // F89.c.1 — when the user clicks a neighbour in the "Similar" section
  // we swap the preview target in place rather than closing + reopening
  // the dialog. ``overrideDoc`` takes priority over the parent-supplied
  // ``doc`` prop while the dialog is open; cleared on close.
  const [overrideDoc, setOverrideDoc] = React.useState<DocumentResponse | null>(
    null
  );
  const activeDoc = overrideDoc ?? doc;
  const activeDocId = activeDoc?.id;

  React.useEffect(() => {
    if (!activeDocId || !open) {
      setMetadata(null);
      return;
    }
    setLoading(true);
    getDocumentMetadata({ path: { document_id: activeDocId } }).then(
      ({ data }) => {
        if (data) setMetadata(data);
        setLoading(false);
      }
    );
  }, [activeDocId, open]);

  React.useEffect(() => {
    if (!open) setOverrideDoc(null);
  }, [open]);

  const handleSelectNeighbour = React.useCallback(
    async (documentId: string) => {
      // Prefer the list-cache hydrated by the documents page — zero
      // extra fetch in the common (HR) case. Admin cross-owner hits
      // the fallback.
      const cached = queryClient.getQueryData<DocumentResponse[]>(
        listDocumentsOptions().queryKey
      );
      const hit = cached?.find((d) => d.id === documentId);
      if (hit) {
        setOverrideDoc(hit);
        return;
      }
      const { data, error } = await getDocument({
        path: { document_id: documentId },
      });
      if (error) {
        toast.error("Could not load that document.");
        return;
      }
      if (data) setOverrideDoc(data);
    },
    [queryClient]
  );

  if (!activeDoc) return null;

  const handleDownload = async () => {
    const { data, error } = await downloadDocument({
      path: { document_id: activeDoc.id },
    });
    if (error) {
      toast.error("Download failed");
      return;
    }
    if (data instanceof Blob) {
      const url = URL.createObjectURL(data);
      const a = Object.assign(document.createElement("a"), {
        href: url,
        download: activeDoc.filename,
      });
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const meta = metadata?.metadata_ as Record<string, unknown> | null;
  const skills: string[] = Array.isArray(meta?.skills) ? meta.skills : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="bg-muted flex size-10 items-center justify-center rounded">
              <FileTextIcon className="text-muted-foreground size-5" />
            </div>
            <div>
              <DialogTitle className="text-left">
                {activeDoc.filename}
              </DialogTitle>
              <Typography variant="muted" className="text-xs">
                {formatFileSize(activeDoc.size_bytes)} &middot;{" "}
                {formatDateTime(activeDoc.created_at)}
              </Typography>
            </div>
          </div>
        </DialogHeader>

        <div key={activeDoc.id} className="flex-1 overflow-auto">
          <div className="mb-4 rounded-lg border p-4">
            <Typography variant="h6" className="mb-3">
              Document Info
            </Typography>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Typography variant="muted" className="text-xs">
                  Type
                </Typography>
                <Badge variant="outline" className="mt-1 capitalize">
                  {activeDoc.document_type ?? "unclassified"}
                </Badge>
              </div>
              <div>
                <Typography variant="muted" className="text-xs">
                  Status
                </Typography>
                <Badge
                  variant={
                    activeDoc.status === "ready" ? "default" : "secondary"
                  }
                  className="mt-1 capitalize"
                >
                  {activeDoc.status}
                </Badge>
              </div>
              {skills.length > 0 && (
                <div className="sm:col-span-2">
                  <Typography variant="muted" className="text-xs">
                    Skills
                  </Typography>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {skills.map((s) => (
                      <Badge
                        key={s}
                        variant="outline"
                        className={cn("text-xs", skillHueClass(s))}
                      >
                        {s}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <Separator className="my-4" />

          <div className="mb-4">
            <Typography variant="h6" className="mb-3">
              Preview
            </Typography>
            <DocumentViewer
              documentId={activeDoc.id}
              downloadFallback={handleDownload}
            />
          </div>

          <Separator className="my-4" />

          <div>
            <Typography variant="h6" className="mb-3">
              Extracted Content
            </Typography>
            {loading ? (
              <div className="bg-muted/50 animate-pulse rounded-lg p-8" />
            ) : metadata?.extracted_text ? (
              <div className="bg-muted/50 rounded-lg p-4">
                <pre className="max-h-64 overflow-auto font-mono text-sm whitespace-pre-wrap">
                  {metadata.extracted_text}
                </pre>
              </div>
            ) : activeDoc.status === "processing" ||
              activeDoc.status === "pending" ? (
              <div className="bg-muted/50 rounded-lg p-8 text-center">
                <Typography variant="muted">
                  Document is being processed...
                </Typography>
              </div>
            ) : (
              <div className="bg-muted/50 rounded-lg p-8 text-center">
                <Typography variant="muted">
                  No extracted text available.
                </Typography>
              </div>
            )}
          </div>

          <Separator className="my-4" />

          <SimilarDocuments
            document={activeDoc}
            enabled={open}
            onSelect={handleSelectNeighbour}
          />
        </div>

        <Separator className="my-4" />

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            <XIcon className="size-4" data-icon="inline-start" />
            Close
          </Button>
          <Button onClick={handleDownload}>
            <DownloadIcon className="size-4" data-icon="inline-start" />
            Download
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
