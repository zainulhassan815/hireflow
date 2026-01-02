import { DownloadIcon, FileTextIcon, XIcon } from "lucide-react";

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

interface Document {
  id: string;
  name: string;
  type: string;
  size: string;
  uploadedAt: string;
  status: string;
  pages?: number;
  extractedText?: string;
}

interface DocumentPreviewProps {
  document: Document | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DocumentPreview({
  document,
  open,
  onOpenChange,
}: DocumentPreviewProps) {
  if (!document) return null;

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[80vh] max-w-2xl flex-col overflow-hidden">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-muted flex size-10 items-center justify-center rounded">
                <FileTextIcon className="text-muted-foreground size-5" />
              </div>
              <div>
                <DialogTitle className="text-left">{document.name}</DialogTitle>
                <Typography variant="muted" className="text-xs">
                  {document.size} • {document.pages || 1} page
                  {(document.pages || 1) > 1 ? "s" : ""}
                </Typography>
              </div>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-auto">
          {/* Metadata Section */}
          <div className="mb-4 rounded-lg border p-4">
            <Typography variant="h6" className="mb-3">
              Document Metadata
            </Typography>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Typography variant="muted" className="text-xs">
                  Type
                </Typography>
                <Badge variant="outline" className="mt-1">
                  {document.type.charAt(0).toUpperCase() +
                    document.type.slice(1)}
                </Badge>
              </div>
              <div>
                <Typography variant="muted" className="text-xs">
                  Status
                </Typography>
                <Badge
                  variant={
                    document.status === "completed" ? "default" : "secondary"
                  }
                  className="mt-1"
                >
                  {document.status.charAt(0).toUpperCase() +
                    document.status.slice(1)}
                </Badge>
              </div>
              <div>
                <Typography variant="muted" className="text-xs">
                  File Size
                </Typography>
                <Typography variant="small" className="mt-1 block">
                  {document.size}
                </Typography>
              </div>
              <div>
                <Typography variant="muted" className="text-xs">
                  Uploaded
                </Typography>
                <Typography variant="small" className="mt-1 block">
                  {formatDate(document.uploadedAt)}
                </Typography>
              </div>
            </div>
          </div>

          <Separator className="my-4" />

          {/* Extracted Text Section */}
          <div>
            <Typography variant="h6" className="mb-3">
              Extracted Content
            </Typography>
            {document.extractedText ? (
              <div className="bg-muted/50 rounded-lg p-4">
                <pre className="font-mono text-sm whitespace-pre-wrap">
                  {document.extractedText}
                </pre>
              </div>
            ) : document.status === "processing" ? (
              <div className="bg-muted/50 rounded-lg p-8 text-center">
                <Typography variant="muted">
                  Document is being processed. Text extraction in progress...
                </Typography>
              </div>
            ) : (
              <div className="bg-muted/50 rounded-lg p-8 text-center">
                <Typography variant="muted">
                  No extracted text available for this document.
                </Typography>
              </div>
            )}
          </div>
        </div>

        <Separator className="my-4" />

        {/* Actions */}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            <XIcon className="size-4" data-icon="inline-start" />
            Close
          </Button>
          <Button>
            <DownloadIcon className="size-4" data-icon="inline-start" />
            Download
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
