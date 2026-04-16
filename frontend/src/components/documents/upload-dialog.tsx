import * as React from "react";
import { CloudUploadIcon, FileIcon, XIcon } from "lucide-react";

import { documentsUploadDocument, type DocumentResponse } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Typography } from "@/components/ui/typography";
import { formatFileSize } from "@/lib/utils";
import { toast } from "sonner";

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded?: (doc: DocumentResponse) => void;
}

interface UploadingFile {
  file: File;
  status: "uploading" | "completed" | "error";
}

const VALID_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "image/tiff",
];

export function UploadDialog({
  open,
  onOpenChange,
  onUploaded,
}: UploadDialogProps) {
  const [isDragging, setIsDragging] = React.useState(false);
  const [uploadingFiles, setUploadingFiles] = React.useState<UploadingFile[]>(
    []
  );
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(Array.from(e.dataTransfer.files));
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = (files: File[]) => {
    const validFiles = files.filter((file) => {
      if (!VALID_TYPES.includes(file.type)) {
        toast.error(`${file.name}: Unsupported file type`);
        return false;
      }
      if (file.size > 10 * 1024 * 1024) {
        toast.error(`${file.name}: File too large (max 10MB)`);
        return false;
      }
      return true;
    });

    for (const file of validFiles) {
      uploadFile(file);
    }
  };

  const uploadFile = async (file: File) => {
    setUploadingFiles((prev) => [
      ...prev,
      { file, status: "uploading" as const },
    ]);

    const { data, error } = await documentsUploadDocument({
      body: { file },
    });

    if (error) {
      setUploadingFiles((prev) =>
        prev.map((f) =>
          f.file === file ? { ...f, status: "error" as const } : f
        )
      );
      const message =
        typeof error === "object" && "detail" in error
          ? (error as { detail: string }).detail
          : "Upload failed";
      toast.error(`${file.name}: ${message}`);
      return;
    }

    setUploadingFiles((prev) =>
      prev.map((f) =>
        f.file === file ? { ...f, status: "completed" as const } : f
      )
    );
    toast.success(`${file.name} uploaded`);
    if (data) {
      onUploaded?.(data);
    }
  };

  const removeFile = (index: number) => {
    setUploadingFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleClose = () => {
    if (uploadingFiles.some((f) => f.status === "uploading")) {
      toast.error("Please wait for uploads to complete");
      return;
    }
    setUploadingFiles([]);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload Documents</DialogTitle>
          <DialogDescription>
            Upload PDF, Word documents, or images for processing
          </DialogDescription>
        </DialogHeader>

        <div
          className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
            isDragging
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:border-primary/50"
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <CloudUploadIcon className="text-muted-foreground mb-4 size-12" />
          <Typography variant="small" className="text-center font-medium">
            Drag and drop files here
          </Typography>
          <Typography variant="muted" className="mt-1 text-center text-xs">
            or click to browse
          </Typography>
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={() => fileInputRef.current?.click()}
          >
            Select Files
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tiff"
            onChange={handleFileSelect}
            className="hidden"
          />
          <Typography variant="muted" className="mt-4 text-center text-xs">
            Supported: PDF, DOC, DOCX, PNG, JPG, TIFF (max 10MB each)
          </Typography>
        </div>

        {uploadingFiles.length > 0 && (
          <div className="max-h-48 space-y-2 overflow-auto">
            {uploadingFiles.map((upload, index) => (
              <div
                key={index}
                className="flex items-center gap-3 rounded-lg border p-3"
                data-uploading={upload.status === "uploading" || undefined}
              >
                <div className="bg-muted flex size-10 items-center justify-center rounded">
                  <FileIcon className="text-muted-foreground size-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <Typography variant="small" className="truncate font-medium">
                    {upload.file.name}
                  </Typography>
                  <div className="flex items-center gap-2">
                    {upload.status === "uploading" ? (
                      <Progress value={50} className="h-1.5 flex-1 animate-pulse" />
                    ) : (
                      <Typography variant="muted" className="text-xs">
                        {upload.status === "completed" ? "Done" : "Failed"}
                      </Typography>
                    )}
                  </div>
                  <Typography variant="muted" className="text-xs">
                    {formatFileSize(upload.file.size)}
                  </Typography>
                </div>
                {upload.status !== "uploading" && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => removeFile(index)}
                  >
                    <XIcon className="size-4" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            {uploadingFiles.some((f) => f.status === "completed")
              ? "Done"
              : "Cancel"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
