import * as React from "react";
import { FileTextIcon, SearchIcon, SparklesIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { searchDocuments, type SearchResultItem } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { HighlightedText } from "@/components/highlighted-text";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Typography } from "@/components/ui/typography";
import { extractApiError } from "@/lib/api-errors";
import { cn, skillHueClass } from "@/lib/utils";

const CONFIDENCE_DISPLAY: Record<
  "high" | "medium" | "low",
  { label: string; className: string; tooltip: string }
> = {
  high: {
    label: "Strong match",
    className: "border-success text-success",
    tooltip: "Top retrieved chunk is close to your query in meaning.",
  },
  medium: {
    label: "Partial match",
    className: "border-warning text-warning",
    tooltip: "Some relevant chunks found, but the match isn't tight.",
  },
  low: {
    label: "Weak match",
    className: "border-muted-foreground text-muted-foreground",
    tooltip: "Retrieval scraped something, but nothing highly relevant.",
  },
};

export function SearchPage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isSearching, setIsSearching] = React.useState(false);
  const [searchResults, setSearchResults] = React.useState<SearchResultItem[]>(
    []
  );
  const [queryTimeMs, setQueryTimeMs] = React.useState<number | null>(null);
  const [hasSearched, setHasSearched] = React.useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setHasSearched(true);

    const { data, error } = await searchDocuments({
      body: { query: searchQuery },
    });

    if (error) {
      toast.error(extractApiError(error).message);
      setIsSearching(false);
      return;
    }

    setSearchResults(data?.results ?? []);
    setQueryTimeMs(data?.query_time_ms ?? null);
    setIsSearching(false);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Typography variant="h3">Search</Typography>
          <Typography variant="muted">
            Semantic search across your document library.
          </Typography>
        </div>
        <Button variant="outline" onClick={() => navigate("/qa")}>
          <SparklesIcon className="size-4" data-icon="inline-start" />
          Ask a question instead
        </Button>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            placeholder="Search documents using natural language…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button type="submit" disabled={isSearching}>
          {isSearching ? "Searching…" : "Search"}
        </Button>
      </form>

      {searchResults.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Typography variant="h5">
              {searchResults.length} Results
              {queryTimeMs != null && (
                <span className="text-muted-foreground ml-2 text-sm font-normal">
                  ({queryTimeMs}ms)
                </span>
              )}
            </Typography>
          </div>

          <div className="space-y-3">
            {searchResults.map((result) => (
              <Card key={result.document_id}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="bg-muted flex size-10 items-center justify-center rounded">
                        <FileTextIcon className="text-muted-foreground size-5" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <Typography variant="small" className="font-medium">
                            {result.filename}
                          </Typography>
                          {result.document_type && (
                            <Badge
                              variant="outline"
                              className="text-xs capitalize"
                            >
                              {result.document_type}
                            </Badge>
                          )}
                        </div>
                        {result.highlights.length > 0 && (
                          <Typography
                            variant="muted"
                            className="mt-1 line-clamp-3 text-sm"
                          >
                            <HighlightedText
                              text={result.highlights[0].text}
                              spans={result.highlights[0].match_spans}
                            />
                          </Typography>
                        )}
                        {result.metadata &&
                          Array.isArray(
                            (result.metadata as Record<string, unknown>).skills
                          ) && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {(
                                (result.metadata as Record<string, unknown>)
                                  .skills as string[]
                              )
                                .slice(0, 8)
                                .map((skill: string) => (
                                  <Badge
                                    key={skill}
                                    variant="outline"
                                    className={cn(
                                      "text-xs",
                                      skillHueClass(skill)
                                    )}
                                  >
                                    {skill}
                                  </Badge>
                                ))}
                            </div>
                          )}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {result.confidence &&
                        CONFIDENCE_DISPLAY[result.confidence] && (
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    CONFIDENCE_DISPLAY[result.confidence]
                                      .className
                                  )}
                                >
                                  {CONFIDENCE_DISPLAY[result.confidence].label}
                                </Badge>
                              }
                            />
                            <TooltipContent>
                              {CONFIDENCE_DISPLAY[result.confidence].tooltip}
                            </TooltipContent>
                          </Tooltip>
                        )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {hasSearched && searchResults.length === 0 && !isSearching && (
        <div className="py-12 text-center">
          <SearchIcon className="text-muted-foreground mx-auto size-12 opacity-50" />
          <Typography variant="h5" className="mt-4">
            No results found
          </Typography>
          <Typography variant="muted" className="mt-1">
            Try different keywords or upload more documents.
          </Typography>
          <Button
            variant="outline"
            onClick={() => navigate("/qa")}
            className="mt-4"
          >
            <SparklesIcon className="size-4" data-icon="inline-start" />
            Try asking a question
          </Button>
        </div>
      )}
    </div>
  );
}
