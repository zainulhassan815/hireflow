import { uploadDocument, type DocumentResponse } from "@/api";
import { extractApiError } from "@/lib/api-errors";
import { toast } from "sonner";

const VALID_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "image/tiff",
];

const MAX_SIZE_BYTES = 10 * 1024 * 1024;

export interface UploadOutcome {
  succeeded: DocumentResponse[];
  failed: File[];
}

function validateFile(file: File): string | null {
  if (!VALID_TYPES.includes(file.type)) return "Unsupported file type";
  if (file.size > MAX_SIZE_BYTES) return "File too large (max 10MB)";
  return null;
}

export async function uploadFiles(files: File[]): Promise<UploadOutcome> {
  const outcome: UploadOutcome = { succeeded: [], failed: [] };
  for (const file of files) {
    const reason = validateFile(file);
    if (reason) {
      toast.error(`${file.name}: ${reason}`);
      outcome.failed.push(file);
      continue;
    }
    const { data, error } = await uploadDocument({ body: { file } });
    if (error) {
      toast.error(`${file.name}: ${extractApiError(error).message}`);
      outcome.failed.push(file);
      continue;
    }
    if (data) {
      outcome.succeeded.push(data);
    }
  }
  return outcome;
}

export { VALID_TYPES, MAX_SIZE_BYTES };
