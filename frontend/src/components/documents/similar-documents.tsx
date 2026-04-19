import * as React from "react";
import { useQuery, queryOptions } from "@tanstack/react-query";
import { FileIcon, FileTextIcon, ImageIcon, LayersIcon } from "lucide-react";

import {
  findSimilarDocuments,
  type DocumentResponse,
  type SimilarDocument,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Typography } from "@/components/ui/typography";
import { extractApiError } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

const DEFAULT_LIMIT = 5;

const typeIcons: Record<string, React.ElementType> = {
  resume: FileTextIcon,
  report: FileTextIcon,
  contract: FileIcon,
  letter: FileTextIcon,
  other: ImageIcon,
};

// Thin wrapper around the generated POST endpoint so we can consume
// similarity as a cacheable read (react-query). The generated
// ``findSimilarDocumentsMutation`` is shaped for useMutation, but
// semantically this is a fetch-on-open query — wrapping here keeps the
// component idiomatic without diverging from the SDK types.
function similarDocumentsQueryOptions(documentId: string, limit: number) {
  return queryOptions({
    queryKey: ["similarDocuments", documentId, limit],
    queryFn: async () => {
      const { data, error } = await findSimilarDocuments({
        path: { document_id: documentId },
        body: { limit },
      });
      if (error) {
        throw error;
      }
      return data;
    },
  });
}

interface SimilarDocumentsProps {
  document: DocumentResponse;
  enabled: boolean;
  onSelect: (documentId: string) => void;
}

/**
 * Renders the "Similar documents" section of the preview dialog.
 *
 * Lazy-fires on dialog open via ``enabled``; caches per source-doc id so
 * swaps between neighbours are instant on return. Error copy switches on
 * the backend error ``code`` (not ``message``) so backend rewording
 * doesn't break the UI contract.
 */
export function SimilarDocuments({
  document: doc,
  enabled,
  onSelect,
}: SimilarDocumentsProps) {
  const query = useQuery({
    ...similarDocumentsQueryOptions(doc.id, DEFAULT_LIMIT),
    enabled: enabled && doc.status === "ready",
  });

  return (
    <section aria-labelledby="similar-docs-heading">
      <div className="mb-3 flex items-center gap-2">
        <LayersIcon className="text-muted-foreground size-4" />
        <Typography variant="h6" id="similar-docs-heading">
          Similar documents
        </Typography>
      </div>
      <SimilarDocumentsBody query={query} doc={doc} onSelect={onSelect} />
    </section>
  );
}

function SimilarDocumentsBody({
  query,
  doc,
  onSelect,
}: {
  query: ReturnType<
    typeof useQuery<Awaited<ReturnType<typeof findSimilarDocuments>>["data"]>
  >;
  doc: DocumentResponse;
  onSelect: (id: string) => void;
}) {
  if (doc.status !== "ready") {
    return (
      <Typography variant="muted" className="text-sm">
        Available once this document finishes processing.
      </Typography>
    );
  }

  if (query.isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="bg-muted/50 h-12 animate-pulse rounded-lg"
            aria-hidden
          />
        ))}
      </div>
    );
  }

  if (query.isError) {
    const { code, message } = extractApiError(query.error);
    let copy = message;
    if (code === "document_not_indexed") {
      copy =
        "This document isn't in the similarity index yet. Try again in a moment, or ask an admin to re-index.";
    } else if (code === "service_unavailable") {
      copy = "Similarity search is temporarily unavailable.";
    }
    return (
      <Typography variant="muted" className="text-sm">
        {copy}
      </Typography>
    );
  }

  const results: SimilarDocument[] = query.data?.results ?? [];

  if (results.length === 0) {
    return (
      <Typography variant="muted" className="text-sm">
        No similar documents found.
      </Typography>
    );
  }

  return (
    <ul className="flex flex-col gap-1" role="list">
      {results.map((neighbour) => (
        <SimilarRow
          key={neighbour.document_id}
          neighbour={neighbour}
          onSelect={onSelect}
        />
      ))}
    </ul>
  );
}

function SimilarRow({
  neighbour,
  onSelect,
}: {
  neighbour: SimilarDocument;
  onSelect: (id: string) => void;
}) {
  const Icon = typeIcons[neighbour.document_type ?? "other"] ?? FileIcon;
  const percent = Math.round(neighbour.similarity * 100);
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(neighbour.document_id)}
        className={cn(
          "group flex w-full items-center gap-3 rounded-lg border border-transparent px-3 py-2 text-left transition",
          "hover:border-border hover:bg-muted/50",
          "focus-visible:ring-ring focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
        )}
      >
        <div className="bg-muted flex size-8 items-center justify-center rounded">
          <Icon className="text-muted-foreground size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <Typography variant="small" className="truncate font-medium">
            {neighbour.filename}
          </Typography>
          <div className="mt-0.5 flex items-center gap-2">
            <Badge variant="outline" className="text-xs capitalize">
              {neighbour.document_type ?? "—"}
            </Badge>
          </div>
        </div>
        <Typography
          variant="muted"
          className="shrink-0 font-mono text-xs tabular-nums"
        >
          {percent}%
        </Typography>
      </button>
    </li>
  );
}
