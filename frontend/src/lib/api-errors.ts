/**
 * Single entry point for parsing backend error responses into a
 * `{code, message}` pair the UI can render. Backend contract lives in
 * `backend/app/schemas/errors.py`.
 */

type Unknown = Record<string, unknown>;

export type ApiError = {
  code: string;
  message: string;
};

const FALLBACK: ApiError = {
  code: "unknown_error",
  message: "Something went wrong. Please try again.",
};

function isRecord(value: unknown): value is Unknown {
  return typeof value === "object" && value !== null;
}

export function extractApiError(err: unknown): ApiError {
  if (err instanceof Error && err.message) {
    return { code: "client_error", message: err.message };
  }

  if (!isRecord(err)) return FALLBACK;

  if (isRecord(err.error)) {
    const { code, message } = err.error;
    if (typeof code === "string" && typeof message === "string") {
      return { code, message };
    }
  }

  // Legacy FastAPI shape: { detail: "..." } or { detail: [ValidationError] }.
  // Kept so a mid-deploy client doesn't crash on an un-migrated endpoint.
  if (typeof err.detail === "string") {
    return { code: "legacy_error", message: err.detail };
  }
  if (Array.isArray(err.detail) && err.detail.length > 0) {
    const first = err.detail[0];
    if (isRecord(first) && typeof first.msg === "string") {
      return { code: "validation_error", message: first.msg };
    }
  }

  return FALLBACK;
}
