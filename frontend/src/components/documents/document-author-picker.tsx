/**
 * F103.c.2 — author picker for the document detail page.
 *
 * Three states the parent passes via the document's
 * `authored_by` / `authored_by_source` fields:
 *
 *   - Unlinked     → "Not linked" placeholder + "Link to candidate"
 *                    button that opens the picker.
 *   - Auto-linked  → name + "Auto-linked" badge + edit pencil.
 *   - Manual       → name + "Manual override" badge + edit pencil
 *                    + "Clear" button.
 *
 * Operator picks a candidate via a Combobox over `listCandidates`
 * (filtered to the current owner's pool). On submit, calls
 * `updateDocumentAuthor` and refreshes the document query upstream
 * via the `onChanged` callback.
 *
 * The "Saved. Re-embedding…" toast is owned by the parent — the
 * picker just signals success/failure via the callback.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, PencilIcon, UserPlusIcon, XIcon } from "lucide-react";
import { toast } from "sonner";

import {
  getDocumentOptions,
  listCandidatesOptions,
  updateDocumentAuthor,
} from "@/api";
import type {
  AuthorSource,
  CandidateLite,
  DocumentResponse,
} from "@/api/generated";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";

interface Props {
  document: DocumentResponse;
}

export function DocumentAuthorPicker({ document: doc }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);

  const { data: candidatesData } = useQuery({
    ...listCandidatesOptions(),
    enabled: editing,
  });
  // ``listCandidates`` returns a flat array of ``CandidateResponse``
  // (no pagination envelope). Project to ``CandidateLite`` to match
  // the picker's render shape.
  const candidates: CandidateLite[] =
    candidatesData?.map((c) => ({
      id: c.id,
      name: c.name ?? null,
      email: c.email ?? null,
    })) ?? [];

  const mutation = useMutation({
    mutationFn: async (candidateId: string | null) => {
      const { data, error } = await updateDocumentAuthor({
        path: { document_id: doc.id },
        body: { candidate_id: candidateId },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      toast.success("Saved. Re-embedding in the background…");
      // Refresh the doc detail query so the new author state lands.
      void queryClient.invalidateQueries({
        queryKey: getDocumentOptions({ path: { document_id: doc.id } })
          .queryKey,
      });
      setEditing(false);
    },
    onError: () => {
      toast.error("Failed to update author");
    },
  });

  const author = doc.authored_by;
  const source = doc.authored_by_source as AuthorSource | null | undefined;

  // ---- editing form ----
  if (editing) {
    return (
      <div className="flex flex-col gap-2">
        <Combobox<CandidateLite>
          items={candidates}
          // ``itemToStringValue`` keys identity (used for selection
          // tracking + filtering); ``itemToStringLabel`` is the
          // display text the input echoes after a pick.
          itemToStringValue={(c) => c?.id ?? ""}
          itemToStringLabel={(c) =>
            c?.name
              ? `${c.name}${c.email ? ` · ${c.email}` : ""}`
              : (c?.email ?? "Unknown")
          }
          onValueChange={(picked) => {
            // base-ui passes the item object (or null on clear).
            if (picked && typeof picked === "object" && "id" in picked) {
              mutation.mutate(picked.id);
            }
          }}
        >
          <ComboboxInput placeholder="Search candidates by name or email" />
          <ComboboxContent>
            <ComboboxEmpty>No candidates found.</ComboboxEmpty>
            <ComboboxList>
              {(item: CandidateLite) => (
                <ComboboxItem key={item.id} value={item}>
                  <div className="flex flex-col">
                    <span>{item.name ?? "(unnamed)"}</span>
                    {item.email ? (
                      <span className="text-muted-foreground text-xs">
                        {item.email}
                      </span>
                    ) : null}
                  </div>
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditing(false)}
            disabled={mutation.isPending}
          >
            <XIcon className="size-4" data-icon="inline-start" />
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  // ---- unlinked ----
  if (!author) {
    return (
      <div className="flex flex-col gap-2">
        <div className="text-muted-foreground text-sm">
          Not linked to a candidate.
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setEditing(true)}
          className="self-start"
        >
          <UserPlusIcon className="size-4" data-icon="inline-start" />
          Link to candidate
        </Button>
      </div>
    );
  }

  // ---- linked: show name + source badge + edit/clear buttons ----
  const badge =
    source === "manual" ? (
      <Badge variant="secondary" className="text-xs">
        <CheckIcon className="size-3" data-icon="inline-start" />
        Manual override
      </Badge>
    ) : (
      <Badge variant="outline" className="text-xs">
        Auto-linked
      </Badge>
    );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="font-medium">
          {author.name ?? author.email ?? "(unnamed candidate)"}
        </span>
        {badge}
      </div>
      <div className="flex gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setEditing(true)}
          disabled={mutation.isPending}
        >
          <PencilIcon className="size-3.5" data-icon="inline-start" />
          Change
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => mutation.mutate(null)}
          disabled={mutation.isPending}
        >
          <XIcon className="size-3.5" data-icon="inline-start" />
          Clear
        </Button>
      </div>
    </div>
  );
}
