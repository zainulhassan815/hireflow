import { useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { CheckIcon, ExternalLinkIcon, UndoIcon, XIcon } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  listJobApplicationsQueryKey,
  updateApplicationStatusMutation,
  type ApplicationResponse,
  type ApplicationStatus,
} from "@/api";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Typography } from "@/components/ui/typography";
import { cn, skillHueClass } from "@/lib/utils";

/**
 * F44.d.4 — candidate slide-over drawer.
 *
 * Triage-without-leaving-the-list. Click a row in <JobCandidateList>
 * → Sheet opens on the right with candidate header, status + inline
 * action buttons, match score bar, skills, and the F105 DocumentViewer
 * embedded for the candidate's source resume. Escape closes.
 *
 * Status mutation is local to the drawer but writes back into the
 * parent listJobApplications cache, so the list underneath stays
 * in sync. Parent mirrors the freshest row from the cache into the
 * `app` prop on each render, so bulk actions / refresh-scores /
 * row-level flips reflect inside the drawer live.
 *
 * Uses shadcn's Sheet (base-ui Dialog) rather than vaul's Drawer —
 * vaul's direction="right" had a body-not-rendering bug in 1.1.2 on
 * this setup; Sheet's side-right is the first-class primitive here.
 */

interface CandidateDrawerProps {
  app: ApplicationResponse | null;
  onOpenChange: (open: boolean) => void;
  onStatusChanged: () => void;
}

export function CandidateDrawer({
  app,
  onOpenChange,
  onStatusChanged,
}: CandidateDrawerProps) {
  // Hold the last shown app so the exit animation plays against
  // concrete content instead of flashing empty.
  const [lastApp, setLastApp] = React.useState<ApplicationResponse | null>(app);
  React.useEffect(() => {
    if (app) setLastApp(app);
  }, [app]);
  const shown = app ?? lastApp;

  return (
    <Sheet open={!!app} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full p-0 data-[side=right]:sm:max-w-2xl md:max-w-3xl"
      >
        {shown ? (
          <Body
            app={shown}
            onStatusChanged={onStatusChanged}
            onClose={() => onOpenChange(false)}
          />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function Body({
  app,
  onStatusChanged,
  onClose,
}: {
  app: ApplicationResponse;
  onStatusChanged: () => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const queryKey = listJobApplicationsQueryKey({
    path: { job_id: app.job_id },
  });

  const mut = useMutation({
    ...updateApplicationStatusMutation(),
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey });
      const previous =
        queryClient.getQueryData<ApplicationResponse[]>(queryKey);
      const nextStatus = variables.body?.status as ApplicationStatus;
      queryClient.setQueryData<ApplicationResponse[]>(queryKey, (old) =>
        (old ?? []).map((a) =>
          a.id === app.id ? { ...a, status: nextStatus } : a
        )
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(queryKey, ctx.previous);
      toast.error("Status change failed; rolled back.");
    },
    onSuccess: () => onStatusChanged(),
  });

  const setStatus = (status: ApplicationStatus) =>
    mut.mutate({ path: { application_id: app.id }, body: { status } });

  const c = app.candidate;
  const displayName = c.name || c.email || "Unnamed candidate";
  const score100 = Math.round((app.score ?? 0) * 100);
  const updated = new Date(app.updated_at);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <SheetHeader className="flex-row items-start gap-3 border-b p-4 pr-12">
        <Avatar name={c.name} email={c.email} />
        <div className="min-w-0 flex-1">
          <SheetTitle className="truncate">{displayName}</SheetTitle>
          {c.email && (
            <SheetDescription className="truncate">{c.email}</SheetDescription>
          )}
        </div>
        {c.source_document_id && (
          <Link to={`/documents/${c.source_document_id}`} onClick={onClose}>
            <Button variant="outline" size="sm">
              <ExternalLinkIcon className="size-4" data-icon="inline-start" />
              Open full page
            </Button>
          </Link>
        )}
      </SheetHeader>

      <div className="flex-1 overflow-y-auto p-4">
        {/* Status + actions */}
        <div className="bg-muted/30 mb-4 rounded-lg border p-3">
          <div className="mb-2 flex items-center justify-between">
            <Typography
              variant="small"
              className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
            >
              Status
            </Typography>
            <Typography variant="muted" className="text-xs">
              Updated {formatDistanceToNow(updated, { addSuffix: true })}
            </Typography>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusLabel status={app.status} />
            <div className="ml-auto flex gap-1">
              <DrawerActions
                status={app.status}
                onSetStatus={setStatus}
                pending={mut.isPending}
              />
            </div>
          </div>
        </div>

        {/* Match score */}
        <div className="mb-4">
          <Typography
            variant="small"
            className="text-muted-foreground mb-2 block text-xs font-medium tracking-wide uppercase"
          >
            Match score
          </Typography>
          <div className="flex items-center gap-3">
            <div className="bg-muted h-2 flex-1 overflow-hidden rounded-full">
              <div
                className={cn(
                  "h-full rounded-full transition-[width]",
                  score100 >= 80
                    ? "bg-success"
                    : score100 >= 60
                      ? "bg-warning"
                      : "bg-muted-foreground"
                )}
                style={{ width: `${score100}%` }}
              />
            </div>
            <span className="shrink-0 text-lg font-semibold tabular-nums">
              {score100}%
            </span>
          </div>
        </div>

        {/* Skills */}
        {c.skills && c.skills.length > 0 && (
          <div className="mb-4">
            <Typography
              variant="small"
              className="text-muted-foreground mb-2 block text-xs font-medium tracking-wide uppercase"
            >
              Skills
            </Typography>
            <div className="flex flex-wrap gap-1">
              {c.skills.map((skill) => (
                <Badge
                  key={skill}
                  variant="outline"
                  className={cn("text-xs", skillHueClass(skill))}
                >
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        )}

        <Separator className="my-4" />

        {/* Resume */}
        <div>
          <div className="mb-2">
            <Typography
              variant="small"
              className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
            >
              Resume
            </Typography>
          </div>
          {c.source_document_id ? (
            <div className="min-h-[400px]">
              <DocumentViewer documentId={c.source_document_id} />
            </div>
          ) : (
            <div className="bg-muted/40 flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
              <Typography variant="muted" className="text-sm">
                No resume on file for this candidate.
              </Typography>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Avatar({
  name,
  email,
}: {
  name: string | null | undefined;
  email: string | null | undefined;
}) {
  const key = name || email || "?";
  const source = (name ?? email ?? "?").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  const initials =
    parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : source.slice(0, 2).toUpperCase();
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
        skillHueClass(key)
      )}
    >
      {initials}
    </span>
  );
}

function StatusLabel({ status }: { status: ApplicationStatus }) {
  const meta: Record<
    ApplicationStatus,
    { label: string; dot: string; text: string }
  > = {
    new: {
      label: "New",
      dot: "bg-muted-foreground",
      text: "text-muted-foreground",
    },
    shortlisted: {
      label: "Shortlisted",
      dot: "bg-success",
      text: "text-success",
    },
    rejected: {
      label: "Rejected",
      dot: "bg-destructive",
      text: "text-destructive",
    },
    interviewed: { label: "Interviewed", dot: "bg-cat-3", text: "text-cat-3" },
    hired: { label: "Hired", dot: "bg-cat-1", text: "text-cat-1" },
  };
  const m = meta[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", m.text)}>
      <span
        aria-hidden
        className={cn("inline-block size-1.5 rounded-full", m.dot)}
      />
      {m.label}
    </span>
  );
}

function DrawerActions({
  status,
  onSetStatus,
  pending,
}: {
  status: ApplicationStatus;
  onSetStatus: (s: ApplicationStatus) => void;
  pending: boolean;
}) {
  if (status === "interviewed" || status === "hired") {
    return (
      <Typography variant="muted" className="text-xs italic">
        Managed on Kanban
      </Typography>
    );
  }
  if (status === "new") {
    return (
      <>
        <Button
          size="sm"
          onClick={() => onSetStatus("shortlisted")}
          disabled={pending}
        >
          <CheckIcon className="size-4" data-icon="inline-start" />
          Shortlist
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onSetStatus("rejected")}
          disabled={pending}
          className="text-destructive"
        >
          <XIcon className="size-4" data-icon="inline-start" />
          Reject
        </Button>
      </>
    );
  }
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() => onSetStatus("new")}
      disabled={pending}
    >
      <UndoIcon className="size-4" data-icon="inline-start" />
      Undo
    </Button>
  );
}
