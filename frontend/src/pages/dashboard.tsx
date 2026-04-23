import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileTextIcon, UploadIcon, SearchIcon } from "lucide-react";

import {
  listDocumentsOptions,
  listJobsOptions,
  listCandidatesOptions,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Typography } from "@/components/ui/typography";
import {
  cn,
  formatDate,
  formatFileSize,
  typeBadgeClass,
  typeIconClass,
} from "@/lib/utils";
import { useAuth } from "@/providers/use-auth";

// F90.d — semantic status badge color map (ready/processing).
// pending stays on outline variant; failed stays on destructive.
const statusBadgeClass: Record<string, string> = {
  ready: "bg-success text-success-foreground border-transparent",
  processing: "bg-warning text-warning-foreground border-transparent",
};

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const { data: documents = [], isLoading: docsLoading } = useQuery({
    ...listDocumentsOptions(),
    select: (data) => data ?? [],
  });
  const { data: jobs = [], isLoading: jobsLoading } = useQuery({
    ...listJobsOptions(),
    select: (data) => data ?? [],
  });
  const { data: candidates = [], isLoading: candsLoading } = useQuery({
    ...listCandidatesOptions(),
    select: (data) => data ?? [],
  });

  const loading = docsLoading || jobsLoading || candsLoading;

  const stats = {
    documents: documents.length,
    jobs: jobs.length,
    candidates: candidates.length,
    openJobs: jobs.filter((j) => j.status === "open").length,
    processed: documents.filter((d) => d.status === "ready").length,
    processing: documents.filter(
      (d) => d.status === "processing" || d.status === "pending"
    ).length,
    failed: documents.filter((d) => d.status === "failed").length,
  };

  const recent = documents.slice(0, 5);

  if (loading) {
    return (
      <div className="flex flex-col gap-10">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <Skeleton className="h-8 w-56" />
            <Skeleton className="h-4 w-80" />
          </div>
          <div className="flex gap-2">
            <Skeleton className="h-9 w-24" />
            <Skeleton className="h-9 w-24" />
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-12 w-80" />
          <Skeleton className="h-10 w-40" />
          <div className="flex gap-4 border-t pt-4">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-28" />
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <Skeleton className="h-5 w-40" />
          <div className="border">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 border-b p-4">
                <Skeleton className="size-8 shrink-0" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-6 w-20" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // F90.d+ — derive the hero from current state so Priya always
  // sees a clear "here's what to do next" rather than an abstract
  // ratio. Priority order: failed > empty > processing-only > ready.
  const firstName = user?.full_name?.split(" ")[0] ?? "";
  const hero: {
    headline: ReactNode;
    sub: ReactNode | null;
    cta: { label: string; to: string } | null;
  } = (() => {
    if (stats.documents === 0) {
      return {
        headline: (
          <>
            No documents yet. Upload a few resumes and we&rsquo;ll take it from
            there.
          </>
        ),
        sub: null,
        cta: { label: "Upload documents", to: "/documents" },
      };
    }
    const bits: ReactNode[] = [];
    if (stats.processing > 0) {
      bits.push(
        <span key="p" className="text-warning tabular-nums">
          {stats.processing} still processing
        </span>
      );
    }
    if (stats.failed > 0) {
      bits.push(
        <span key="f" className="text-destructive tabular-nums">
          {stats.failed} failed
        </span>
      );
    }
    const sub =
      bits.length === 0 ? null : (
        <span className="text-muted-foreground">
          {bits.map((b, i) => (
            <span key={i}>
              {i > 0 ? " · " : ""}
              {b}
            </span>
          ))}
        </span>
      );
    return {
      headline: (
        <>
          <span className="text-primary tabular-nums">{stats.processed}</span>{" "}
          {stats.processed === 1 ? "document is" : "documents are"} ready to
          screen.
        </>
      ),
      sub,
      cta:
        stats.failed > 0
          ? { label: "Review documents →", to: "/documents" }
          : stats.processed > 0
            ? { label: "Open documents →", to: "/documents" }
            : null,
    };
  })();

  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Typography variant="h3">
            Welcome back{firstName ? `, ${firstName}` : ""}.
          </Typography>
          <Typography variant="muted">
            Here&rsquo;s your library at a glance.
          </Typography>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate("/search")}>
            <SearchIcon className="size-4" data-icon="inline-start" />
            Search
          </Button>
          <Button onClick={() => navigate("/documents")}>
            <UploadIcon className="size-4" data-icon="inline-start" />
            Upload
          </Button>
        </div>
      </div>

      {/* F90.d+ — prose hero. State-derived sentence with one primary
          CTA. Replaces the ratio + right-rail split that was reading
          as a chart rather than a briefing. The left-edge primary
          rule anchors the headline tonally without gradient or glow. */}
      <div className="flex flex-col gap-4">
        <p className="font-display border-primary max-w-[32ch] border-l-[3px] pl-4 text-3xl leading-[1.2] font-semibold tracking-[-0.015em] sm:text-4xl">
          {hero.headline}
        </p>
        {hero.sub && <div className="text-base">{hero.sub}</div>}
        {hero.cta && (
          <div>
            <Button onClick={() => navigate(hero.cta!.to)}>
              {hero.cta.label}
            </Button>
          </div>
        )}

        {/* Unified stat strip — four entities in one horizontal row,
            divided by middots. Secondary information; the hero above
            carries the primary read. Each category gets its own cat
            hue on the numeral so the strip becomes a scannable
            legend: teal/chartreuse/magenta for docs/jobs/candidates
            (primary blue is reserved for the hero anchor). */}
        <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 border-t pt-4 text-sm">
          <span className="tabular-nums">
            <span className="text-cat-5 font-medium">{stats.documents}</span>{" "}
            {stats.documents === 1 ? "document" : "documents"}
          </span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">
            <span className="text-cat-4 font-medium">{stats.jobs}</span>{" "}
            {stats.jobs === 1 ? "job" : "jobs"}
            {stats.jobs > 0 && (
              <span className="text-muted-foreground">
                {" "}
                ({stats.openJobs} open)
              </span>
            )}
          </span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">
            <span className="text-cat-2 font-medium">{stats.candidates}</span>{" "}
            {stats.candidates === 1 ? "candidate" : "candidates"}
          </span>
        </div>
      </div>

      {/* F90.g — skip the Recent Documents block entirely when the
          library is empty; the hero above already carries the empty
          voice + upload CTA. Double-empty was noisy. */}
      {stats.documents > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <Typography variant="h5">Recent Documents</Typography>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              onClick={() => navigate("/documents")}
            >
              View All
            </Button>
          </div>

          <Card className="border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Uploaded</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((doc) => (
                  <TableRow
                    key={doc.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/documents/${doc.id}`)}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            "flex size-8 items-center justify-center rounded",
                            typeIconClass[doc.document_type ?? ""] ??
                              "bg-muted text-muted-foreground"
                          )}
                        >
                          <FileTextIcon className="size-4" />
                        </div>
                        <Typography variant="small" className="font-medium">
                          {doc.filename}
                        </Typography>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={cn(
                          "capitalize",
                          typeBadgeClass[doc.document_type ?? ""]
                        )}
                      >
                        {doc.document_type ?? "—"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography
                        variant="small"
                        className="font-mono tabular-nums"
                      >
                        {formatFileSize(doc.size_bytes)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          doc.status === "failed"
                            ? "destructive"
                            : doc.status === "pending"
                              ? "outline"
                              : "secondary"
                        }
                        className={cn(
                          "capitalize",
                          statusBadgeClass[doc.status]
                        )}
                      >
                        {doc.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Typography variant="muted" className="tabular-nums">
                        {formatDate(doc.created_at)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}
    </div>
  );
}
