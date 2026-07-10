import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PaperclipIcon, TrashIcon, UploadIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  addCandidateAttachments,
  listCandidateAttachmentsOptions,
  listCandidateAttachmentsQueryKey,
  listJobApplicationsQueryKey,
  removeCandidateAttachment,
  uploadDocument,
  type AttachmentRole,
  type CandidateAttachmentResponse,
} from "@/api";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Typography } from "@/components/ui/typography";
import { extractApiError } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

// Roles collapse into four tabs; cover_letter / transcript / other all
// live under "Other" so the switcher stays legible.
const TAB_FOR_ROLE: Record<AttachmentRole, string> = {
  resume: "Resume",
  certificate: "Certificates",
  portfolio: "Portfolio",
  cover_letter: "Other",
  transcript: "Other",
  other: "Other",
};
const TAB_ORDER = ["Resume", "Certificates", "Portfolio", "Other"] as const;

const ROLE_OPTIONS: { value: AttachmentRole; label: string }[] = [
  { value: "certificate", label: "Certificate" },
  { value: "portfolio", label: "Portfolio" },
  { value: "transcript", label: "Transcript" },
  { value: "cover_letter", label: "Cover letter" },
  { value: "resume", label: "Resume" },
  { value: "other", label: "Other" },
];

export function CandidateAttachments({
  candidateId,
  jobId,
}: {
  candidateId: string;
  jobId: string;
}) {
  const queryClient = useQueryClient();
  const attachmentsKey = listCandidateAttachmentsQueryKey({
    path: { candidate_id: candidateId },
  });

  const { data: attachments = [], isLoading } = useQuery({
    ...listCandidateAttachmentsOptions({ path: { candidate_id: candidateId } }),
    select: (data): CandidateAttachmentResponse[] => data ?? [],
  });

  const [activeTab, setActiveTab] = React.useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = React.useState<string | null>(null);
  const [uploadRole, setUploadRole] =
    React.useState<AttachmentRole>("certificate");
  const [busy, setBusy] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const groups = React.useMemo(() => {
    const map = new Map<string, CandidateAttachmentResponse[]>();
    for (const att of attachments) {
      const tab = TAB_FOR_ROLE[att.role];
      (map.get(tab) ?? map.set(tab, []).get(tab)!).push(att);
    }
    return map;
  }, [attachments]);

  const tabs = TAB_ORDER.filter((t) => groups.has(t));

  // Default the active tab / selected doc once data lands or changes.
  React.useEffect(() => {
    if (attachments.length === 0) {
      setActiveTab(null);
      setSelectedDocId(null);
      return;
    }
    const tab = activeTab && groups.has(activeTab) ? activeTab : tabs[0];
    const inTab = groups.get(tab) ?? [];
    const stillThere = inTab.some((a) => a.document_id === selectedDocId);
    if (tab !== activeTab) setActiveTab(tab);
    if (!stillThere) setSelectedDocId(inTab[0]?.document_id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attachments]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: attachmentsKey });
    // Merged skills land on the candidate embedded in the applications list.
    queryClient.invalidateQueries({
      queryKey: listJobApplicationsQueryKey({ path: { job_id: jobId } }),
    });
  };

  const onFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      const pairs: { document_id: string; role: AttachmentRole }[] = [];
      for (const file of Array.from(files)) {
        const { data, error } = await uploadDocument({ body: { file } });
        if (error || !data) {
          toast.error(`${file.name}: ${extractApiError(error).message}`);
          continue;
        }
        pairs.push({ document_id: data.id, role: uploadRole });
      }
      if (pairs.length === 0) return;
      const { error } = await addCandidateAttachments({
        path: { candidate_id: candidateId },
        body: { attachments: pairs },
      });
      if (error) {
        toast.error(extractApiError(error).message);
        return;
      }
      toast.success(
        `Attached ${pairs.length} file${pairs.length === 1 ? "" : "s"}`
      );
      invalidate();
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const detachMut = useMutation({
    mutationFn: (documentId: string) =>
      removeCandidateAttachment({
        path: { candidate_id: candidateId, document_id: documentId },
      }),
    onSuccess: () => {
      toast.success("Detached");
      invalidate();
    },
    onError: () => toast.error("Couldn't detach the file"),
  });

  const activeFiles = activeTab ? (groups.get(activeTab) ?? []) : [];
  const selected =
    activeFiles.find((a) => a.document_id === selectedDocId) ?? activeFiles[0];

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <Typography
          variant="small"
          className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
        >
          Attachments
        </Typography>
        <div className="flex items-center gap-1.5">
          <Select
            value={uploadRole}
            onValueChange={(v) => v && setUploadRole(v as AttachmentRole)}
          >
            <SelectTrigger size="sm" className="h-7 w-[130px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => onFiles(e.target.files)}
          />
          <Button
            variant="outline"
            size="sm"
            className="h-7"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadIcon className="size-3.5" data-icon="inline-start" />
            {busy ? "Uploading…" : "Add files"}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Typography variant="muted" className="text-sm">
          Loading attachments…
        </Typography>
      ) : attachments.length === 0 ? (
        <div className="bg-muted/40 flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
          <PaperclipIcon className="text-muted-foreground mb-2 size-5" />
          <Typography variant="muted" className="text-sm">
            No files attached. Add a resume, certificates, or a portfolio to
            enrich the match.
          </Typography>
        </div>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-1">
            {tabs.map((tab) => {
              const count = groups.get(tab)?.length ?? 0;
              return (
                <Button
                  key={tab}
                  variant={tab === activeTab ? "secondary" : "ghost"}
                  size="sm"
                  className="h-7"
                  onClick={() => {
                    setActiveTab(tab);
                    setSelectedDocId(groups.get(tab)?.[0]?.document_id ?? null);
                  }}
                >
                  {tab}
                  <Badge variant="outline" className="ml-1.5 px-1 text-[10px]">
                    {count}
                  </Badge>
                </Button>
              );
            })}
          </div>

          {activeFiles.length > 1 && (
            <div className="mb-2 flex flex-col gap-1">
              {activeFiles.map((att) => (
                <div
                  key={att.document_id}
                  className={cn(
                    "flex items-center gap-2 rounded-md border px-2 py-1 text-sm",
                    att.document_id === selected?.document_id
                      ? "border-primary bg-muted/50"
                      : "hover:bg-muted/30"
                  )}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left"
                    onClick={() => setSelectedDocId(att.document_id)}
                  >
                    {att.filename}
                  </button>
                  <DetachButton
                    onDetach={() => detachMut.mutate(att.document_id)}
                    pending={detachMut.isPending}
                  />
                </div>
              ))}
            </div>
          )}

          {selected && (
            <div className="mb-2 flex items-center justify-end">
              {activeFiles.length <= 1 && (
                <DetachButton
                  onDetach={() => detachMut.mutate(selected.document_id)}
                  pending={detachMut.isPending}
                  label="Detach"
                />
              )}
            </div>
          )}

          {selected && (
            <div className="min-h-[400px]">
              <DocumentViewer documentId={selected.document_id} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function DetachButton({
  onDetach,
  pending,
  label,
}: {
  onDetach: () => void;
  pending: boolean;
  label?: string;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="text-destructive h-6 px-1.5"
      disabled={pending}
      onClick={onDetach}
    >
      <TrashIcon
        className="size-3.5"
        data-icon={label ? "inline-start" : undefined}
      />
      {label}
    </Button>
  );
}
