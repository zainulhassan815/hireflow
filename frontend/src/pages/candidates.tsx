import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { SearchIcon, UsersIcon } from "lucide-react";

import { listCandidatesOptions } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Typography } from "@/components/ui/typography";

export function CandidatesPage() {
  const [searchQuery, setSearchQuery] = React.useState("");

  const { data: candidates = [], isLoading } = useQuery({
    ...listCandidatesOptions(),
    select: (data) => data ?? [],
  });

  const filtered = candidates.filter((c) => {
    const q = searchQuery.toLowerCase();
    return (
      (c.name ?? "").toLowerCase().includes(q) ||
      (c.email ?? "").toLowerCase().includes(q) ||
      c.skills.some((s) => s.toLowerCase().includes(q))
    );
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Spinner className="size-8" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Typography variant="h3">Candidates</Typography>
        <Typography variant="muted">
          Candidates extracted from uploaded resumes
        </Typography>
      </div>

      <div className="relative max-w-sm min-w-[200px]">
        <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          placeholder="Search by name, email, or skill..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      {candidates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <UsersIcon className="text-muted-foreground size-12" />
          <Typography variant="h4" className="mt-4">
            No candidates yet
          </Typography>
          <Typography variant="muted" className="mt-1">
            Upload resumes and create candidates from the Documents page
          </Typography>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Skills</TableHead>
                <TableHead>Experience</TableHead>
                <TableHead>Education</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Typography variant="small" className="font-medium">
                      {c.name || "—"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="muted">{c.email || "—"}</Typography>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {c.skills.slice(0, 5).map((s) => (
                        <Badge key={s} variant="secondary" className="text-xs">
                          {s}
                        </Badge>
                      ))}
                      {c.skills.length > 5 && (
                        <Badge variant="outline" className="text-xs">
                          +{c.skills.length - 5}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Typography variant="small">
                      {c.experience_years != null
                        ? `${c.experience_years} yr${c.experience_years !== 1 ? "s" : ""}`
                        : "—"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="small">
                      {c.education?.join(", ") || "—"}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
