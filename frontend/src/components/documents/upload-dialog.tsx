import * as React from "react";
import { CloudUploadIcon, FileIcon, XIcon } from "lucide-react";

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
import { toast } from "sonner";

interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface UploadingFile {
  file: File;
  progress: number;
  status: "uploading" | "completed" | "error";
}

export function UploadDialog({ open, onOpenChange }: UploadDialogProps) {
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
    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      handleFiles(files);
    }
  };

  const handleFiles = (files: File[]) => {
    const validTypes = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "image/png",
      "image/jpeg",
      "image/tiff",
    ];

    const validFiles = files.filter((file) => {
      if (!validTypes.includes(file.type)) {
        toast.error(`${file.name}: Invalid file type`);
        return false;
      }
      if (file.size > 25 * 1024 * 1024) {
        toast.error(`${file.name}: File too large (max 25MB)`);
        return false;
      }
      return true;
    });

    if (validFiles.length === 0) return;

    const newFiles: UploadingFile[] = validFiles.map((file) => ({
      file,
      progress: 0,
      status: "uploading" as const,
    }));

    setUploadingFiles((prev) => [...prev, ...newFiles]);

    // Simulate upload progress
    newFiles.forEach((uploadFile, index) => {
      simulateUpload(uploadingFiles.length + index);
    });
  };

  const simulateUpload = (index: number) => {
    let progress = 0;
    const interval = setInterval(() => {
      progress += Math.random() * 15;
      if (progress >= 100) {
        progress = 100;
        clearInterval(interval);
        setUploadingFiles((prev) =>
          prev.map((f, i) =>
            i === index ? { ...f, progress: 100, status: "completed" } : f
          )
        );
        toast.success(`File uploaded successfully`);
      } else {
        setUploadingFiles((prev) =>
          prev.map((f, i) => (i === index ? { ...f, progress } : f))
        );
      }
    }, 200);
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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

        {/* Drop Zone */}
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
            Supported: PDF, DOC, DOCX, PNG, JPG, TIFF (max 25MB each)
          </Typography>
        </div>

        {/* Uploading Files */}
        {uploadingFiles.length > 0 && (
          <div className="max-h-48 space-y-2 overflow-auto">
            {uploadingFiles.map((upload, index) => (
              <div
                key={index}
                className="flex items-center gap-3 rounded-lg border p-3"
              >
                <div className="bg-muted flex size-10 items-center justify-center rounded">
                  <FileIcon className="text-muted-foreground size-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <Typography variant="small" className="truncate font-medium">
                    {upload.file.name}
                  </Typography>
                  <div className="flex items-center gap-2">
                    <Progress
                      value={upload.progress}
                      className="h-1.5 flex-1"
                    />
                    <Typography variant="muted" className="text-xs">
                      {upload.status === "completed"
                        ? "Done"
                        : `${Math.round(upload.progress)}%`}
                    </Typography>
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
