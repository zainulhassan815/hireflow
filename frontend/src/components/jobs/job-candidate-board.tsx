import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRightIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  listJobApplicationsQueryKey,
  updateApplicationStatusMutation,
  type ApplicationResponse,
  type ApplicationStatus,
} from "@/api";
import { CandidateDrawer } from "@/components/jobs/candidate-drawer";
import { Badge } from "@/components/ui/badge";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Typography } from "@/components/ui/typography";
import { cn, skillHueClass } from "@/lib/utils";

/**
 * F93.a/b — Kanban view of a job's applications.
 *
 * Five fixed columns mirroring the ApplicationStatus enum. Drag a
 * card between columns to flip its status; the backend call is the
 * existing single-row PATCH. Within-column drags are a no-op in
 * F93.a (ordering by match score). F93.c will add column_position
 * + a reorder endpoint when users actually need hand-ranking.
 *
 * Uses @dnd-kit/core for accessibility (keyboard + touch + screen
 * reader announcements). DragOverlay renders the lifted card
 * outside document flow so the source column doesn't reflow.
 *
 * Filters (search / score tier / status multi-select) are owned by
 * JobCandidateList today. The Kanban accepts the already-filtered
 * `applications` list, so filter state carries through the view
 * toggle once filter state is lifted (follow-up).
 */

const COLUMNS: {
  id: ApplicationStatus;
  label: string;
  dot: string;
  headerClass: string;
}[] = [
  {
    id: "new",
    label: "New",
    dot: "bg-muted-foreground",
    headerClass: "text-muted-foreground",
  },
  {
    id: "shortlisted",
    label: "Shortlisted",
    dot: "bg-success",
    headerClass: "text-success",
  },
  {
    id: "interviewed",
    label: "Interviewed",
    dot: "bg-cat-3",
    headerClass: "text-cat-3",
  },
  { id: "hired", label: "Hired", dot: "bg-cat-1", headerClass: "text-cat-1" },
  {
    id: "rejected",
    label: "Rejected",
    dot: "bg-destructive",
    headerClass: "text-muted-foreground",
  },
];

interface JobCandidateBoardProps {
  applications: ApplicationResponse[];
  onStatusChanged: () => void;
}

export function JobCandidateBoard({
  applications,
  onStatusChanged,
}: JobCandidateBoardProps) {
  const queryClient = useQueryClient();
  const [drawerAppId, setDrawerAppId] = React.useState<string | null>(null);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  // Track the last status the dragged card hovered over, so the
  // visual preview (landing in column X) is consistent with drop.
  const [hoverStatus, setHoverStatus] =
    React.useState<ApplicationStatus | null>(null);

  const jobId = applications[0]?.job_id;
  const queryKey = jobId
    ? listJobApplicationsQueryKey({ path: { job_id: jobId } })
    : null;

  // Group by status — columns render their slice. Sort within a
  // column by match score desc so top matches land at the top of
  // their column naturally.
  const byStatus = React.useMemo(() => {
    const map = new Map<ApplicationStatus, ApplicationResponse[]>();
    for (const col of COLUMNS) map.set(col.id, []);
    for (const app of applications) {
      const bucket = map.get(app.status);
      if (bucket) bucket.push(app);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    }
    return map;
  }, [applications]);

  const activeApp = activeId
    ? (applications.find((a) => a.id === activeId) ?? null)
    : null;

  const mut = useMutation({
    ...updateApplicationStatusMutation(),
    onMutate: async (variables) => {
      if (!queryKey) return { previous: undefined };
      await queryClient.cancelQueries({ queryKey });
      const previous =
        queryClient.getQueryData<ApplicationResponse[]>(queryKey);
      const appId = variables.path?.application_id as string;
      const nextStatus = variables.body?.status as ApplicationStatus;
      queryClient.setQueryData<ApplicationResponse[]>(queryKey, (old) =>
        (old ?? []).map((a) =>
          a.id === appId ? { ...a, status: nextStatus } : a
        )
      );
      return { previous };
    },
    onError: (_e, _v, ctx) => {
      if (queryKey && ctx?.previous)
        queryClient.setQueryData(queryKey, ctx.previous);
      toast.error("Status change failed; rolled back.");
    },
    onSuccess: () => onStatusChanged(),
  });

  // Dnd-kit sensors: MouseSensor + TouchSensor. TouchSensor has a
  // 200ms delay so vertical scroll on mobile doesn't accidentally
  // initiate a drag. The activationConstraint on MouseSensor
  // requires 5px of movement before a drag starts — prevents
  // click-and-release accidentally opening the drawer.
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 200, tolerance: 5 },
    })
  );

  const onDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
    const app = applications.find((a) => a.id === event.active.id);
    setHoverStatus(app?.status ?? null);
  };

  const onDragOver = (event: { over: { id: string | number } | null }) => {
    if (event.over) setHoverStatus(event.over.id as ApplicationStatus);
  };

  const onDragEnd = (event: DragEndEvent) => {
    setActiveId(null);
    setHoverStatus(null);
    const { active, over } = event;
    if (!over) return;
    const appId = active.id as string;
    const target = over.id as ApplicationStatus;
    const app = applications.find((a) => a.id === appId);
    if (!app || app.status === target) return;
    mut.mutate({ path: { application_id: appId }, body: { status: target } });
  };

  return (
    // Trello / Linear / Lever pattern: the board fills the viewport's
    // remaining vertical space, columns stretch to equal height,
    // and each column scrolls independently. `min-w-0` (horizontal)
    // keeps the 5 × 288px columns from pushing the page sideways;
    // `h-[calc(100dvh-14rem)]` gives the board a definite height so
    // its inner flex-row can allocate that height to each column.
    // 14rem is empirically tuned to the chrome above the board
    // (SidebarInset padding + header block + filter bar + toggle).
    <div className="flex h-[calc(100dvh-14rem)] min-h-[420px] min-w-0 flex-col gap-3">
      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
      >
        <div className="flex h-full min-h-0 min-w-0 gap-3 overflow-x-auto pb-2">
          {COLUMNS.map((col) => {
            const cards = byStatus.get(col.id) ?? [];
            return (
              <KanbanColumn
                key={col.id}
                id={col.id}
                label={col.label}
                dot={col.dot}
                headerClass={col.headerClass}
                count={cards.length}
                isHoverTarget={hoverStatus === col.id && activeId !== null}
              >
                {cards.map((app) => (
                  <KanbanCard
                    key={app.id}
                    app={app}
                    onOpen={() => setDrawerAppId(app.id)}
                    dimmed={activeId === app.id}
                  />
                ))}
              </KanbanColumn>
            );
          })}
        </div>

        <DragOverlay
          // Disable dnd-kit's default drop animation. By default the
          // overlay animates back to the *original* source rect — but
          // we optimistically moved the card to a different column on
          // drop, so that animation is aimed at stale geometry and
          // reads as "snap back". Dropping it entirely makes the
          // overlay disappear at the drop point while the re-rendered
          // card lands in its new column immediately.
          dropAnimation={null}
        >
          {activeApp ? <KanbanCardPreview app={activeApp} /> : null}
        </DragOverlay>
      </DndContext>

      <CandidateDrawer
        app={
          drawerAppId
            ? (applications.find((a) => a.id === drawerAppId) ?? null)
            : null
        }
        onOpenChange={(open) => {
          if (!open) setDrawerAppId(null);
        }}
        onStatusChanged={onStatusChanged}
      />
    </div>
  );
}

/* ------------------------------- Column -------------------------------- */

function KanbanColumn({
  id,
  label,
  dot,
  headerClass,
  count,
  isHoverTarget,
  children,
}: {
  id: ApplicationStatus;
  label: string;
  dot: string;
  headerClass: string;
  count: number;
  isHoverTarget: boolean;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const highlight = isOver || isHoverTarget;

  return (
    // Column fills the board's height via `h-full`. Header is
    // `shrink-0` so it stays pinned at the top even when the card
    // list below it overflows. The droppable region (`setNodeRef`)
    // is the scroll container itself — dragging over any part of
    // the scroll area registers the column as the drop target.
    <div
      className={cn(
        "bg-muted/30 flex h-full w-72 shrink-0 flex-col gap-2 rounded-lg border p-2 transition-colors",
        highlight && "bg-primary/5 border-primary/40"
      )}
    >
      <div className="flex shrink-0 items-center justify-between px-1 py-1.5">
        <div
          className={cn(
            "flex items-center gap-2 text-sm font-medium",
            headerClass
          )}
        >
          <span
            aria-hidden
            className={cn("inline-block size-1.5 rounded-full", dot)}
          />
          {label}
        </div>
        <span className="text-muted-foreground bg-background rounded-full border px-2 py-0.5 text-[11px] font-semibold tabular-nums">
          {count}
        </span>
      </div>
      <div
        ref={setNodeRef}
        className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto"
        data-column-id={id}
      >
        {children}
        {count === 0 && (
          <div className="text-muted-foreground flex flex-1 items-center justify-center rounded-md border border-dashed p-4 text-center text-xs">
            Drop candidates here
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------- Card -------------------------------- */

function KanbanCard({
  app,
  onOpen,
  dimmed,
}: {
  app: ApplicationResponse;
  onOpen: () => void;
  dimmed: boolean;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: app.id,
  });

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className={cn(
        "group bg-background hover:border-primary/50 relative flex cursor-grab flex-col gap-2 rounded-md border p-3 text-sm shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing",
        (isDragging || dimmed) && "opacity-40"
      )}
    >
      <CardBody app={app} onOpen={onOpen} />
    </div>
  );
}

/** Overlay version — renders at the pointer while dragging. */
function KanbanCardPreview({ app }: { app: ApplicationResponse }) {
  return (
    <div className="bg-background border-primary ring-primary/20 flex w-72 flex-col gap-2 rounded-md border p-3 text-sm shadow-lg ring-2">
      <CardBody app={app} onOpen={() => {}} />
    </div>
  );
}

function CardBody({
  app,
  onOpen,
}: {
  app: ApplicationResponse;
  onOpen: () => void;
}) {
  const c = app.candidate;
  const displayName = c.name || c.email || "Unnamed candidate";
  const score100 = Math.round((app.score ?? 0) * 100);
  const initials = candidateInitials(c.name, c.email);

  return (
    <>
      <div className="flex items-start gap-2">
        <span
          aria-hidden
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
            skillHueClass(c.name || c.email || "?")
          )}
        >
          {initials}
        </span>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onOpen();
            }}
            onPointerDown={(e) => e.stopPropagation()}
            className="focus-visible:ring-ring/50 inline-flex w-full items-center gap-1 rounded text-left font-medium hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            <span className="truncate">{displayName}</span>
            <ChevronRightIcon className="size-3 shrink-0 opacity-40" />
          </button>
          {c.email && (
            <span className="text-muted-foreground block truncate text-xs">
              {c.email}
            </span>
          )}
        </div>
      </div>

      {app.breakdown ? (
        <HoverCard>
          <HoverCardTrigger
            render={
              <div
                onPointerDown={(e) => e.stopPropagation()}
                className="flex cursor-default items-center gap-2"
              >
                <MiniBar score={score100} />
              </div>
            }
          />
          <HoverCardContent align="start" className="w-64">
            <div className="flex flex-col gap-2">
              <Typography
                variant="small"
                className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
              >
                Match breakdown
              </Typography>
              <SignalRow
                label="Skills"
                value={app.breakdown.skill_match}
                weight={0.45}
              />
              <SignalRow
                label="Experience"
                value={app.breakdown.experience_fit}
                weight={0.2}
              />
              <SignalRow
                label="Similarity"
                value={app.breakdown.vector_similarity}
                weight={0.35}
              />
            </div>
          </HoverCardContent>
        </HoverCard>
      ) : (
        <MiniBar score={score100} />
      )}

      {c.skills && c.skills.length > 0 && (
        <div
          className="flex flex-wrap gap-1"
          onPointerDown={(e) => e.stopPropagation()}
        >
          {c.skills.slice(0, 3).map((s) => (
            <Badge
              key={s}
              variant="outline"
              className={cn(
                "h-5 px-1.5 text-[11px] font-normal",
                skillHueClass(s)
              )}
            >
              {s}
            </Badge>
          ))}
          {c.skills.length > 3 && (
            <Badge
              variant="outline"
              className="h-5 px-1.5 text-[11px] font-normal"
            >
              +{c.skills.length - 3}
            </Badge>
          )}
        </div>
      )}
    </>
  );
}

function MiniBar({ score }: { score: number }) {
  const color =
    score >= 80
      ? "bg-success"
      : score >= 60
        ? "bg-warning"
        : "bg-muted-foreground";
  return (
    <div className="flex w-full items-center gap-2">
      <div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
        <div
          className={cn("h-full rounded-full", color)}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-muted-foreground w-8 shrink-0 text-[11px] tabular-nums">
        {score}%
      </span>
    </div>
  );
}

function SignalRow({
  label,
  value,
  weight,
}: {
  label: string;
  value: number;
  weight: number;
}) {
  const pct = Math.round(value * 100);
  const contribution = Math.round(value * weight * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-foreground font-medium">{label}</span>
        <span className="text-muted-foreground tabular-nums">
          {pct}%{" "}
          <span className="text-muted-foreground/70">(+{contribution})</span>
        </span>
      </div>
      <div className="bg-muted h-1 w-full overflow-hidden rounded-full">
        <div
          className="bg-primary h-full rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function candidateInitials(
  name: string | null | undefined,
  email: string | null | undefined
): string {
  const source = (name ?? email ?? "?").trim();
  if (!source || source === "?") return "?";
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return source.slice(0, 2).toUpperCase();
}
