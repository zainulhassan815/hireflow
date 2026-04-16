import { DownloadIcon, FileTextIcon, XIcon } from "lucide-react";

import {
  downloadDocument,
  getDocumentMetadata,
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
import { formatDateTime, formatFileSize } from "@/lib/utils";
import { toast } from "sonner";
import * as React from "react";

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
  const [metadata, setMetadata] =
    React.useState<DocumentMetadataResponse | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!doc || !open) {
      setMetadata(null);
      return;
    }
    setLoading(true);
    getDocumentMetadata({ path: { document_id: doc.id } }).then(({ data }) => {
      if (data) setMetadata(data);
      setLoading(false);
    });
  }, [doc?.id, open]);

  if (!doc) return null;

  const handleDownload = async () => {
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
              <DialogTitle className="text-left">{doc.filename}</DialogTitle>
              <Typography variant="muted" className="text-xs">
                {formatFileSize(doc.size_bytes)} &middot;{" "}
                {formatDateTime(doc.created_at)}
              </Typography>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-auto">
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
                  {doc.document_type ?? "unclassified"}
                </Badge>
              </div>
              <div>
                <Typography variant="muted" className="text-xs">
                  Status
                </Typography>
                <Badge
                  variant={doc.status === "ready" ? "default" : "secondary"}
                  className="mt-1 capitalize"
                >
                  {doc.status}
                </Badge>
              </div>
              {skills.length > 0 && (
                <div className="sm:col-span-2">
                  <Typography variant="muted" className="text-xs">
                    Skills
                  </Typography>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {skills.map((s) => (
                      <Badge key={s} variant="secondary" className="text-xs">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
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
            ) : doc.status === "processing" || doc.status === "pending" ? (
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
