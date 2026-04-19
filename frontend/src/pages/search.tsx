import * as React from "react";
import {
  BotIcon,
  FileTextIcon,
  SearchIcon,
  SendIcon,
  SparklesIcon,
  UserIcon,
} from "lucide-react";

import {
  searchDocuments,
  type SearchResultItem,
  type SourceCitation,
} from "@/api";
import { streamRagAnswer } from "@/api/rag-stream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { HighlightedText } from "@/components/highlighted-text";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Typography } from "@/components/ui/typography";
import { extractApiError } from "@/lib/api-errors";
import { toast } from "sonner";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  model?: string;
  queryTimeMs?: number;
  confidence?: "high" | "medium" | "low" | null;
}

// F81.j — parse assistant prose into text / citation segments.
//
// The F81.d system prompt instructs Claude to cite filenames inline
// like `[alice_resume.pdf]`. This helper turns those into typed
// segments the renderer can walk. A bracketed span is promoted to a
// citation ONLY when its inner text matches a known
// ``SourceCitation.filename`` (exact first, then case-insensitive) —
// unknown brackets stay as plain text so we never show false-positive
// chips (e.g. `[TODO]`, `[note]`).
//
// Streaming-safe: incomplete markers (no closing `]` yet) don't match
// the regex, so they render as plain text until the next delta
// completes them and the next re-render picks them up.
type Segment =
  | { kind: "text"; value: string }
  | { kind: "citation"; citation: SourceCitation };

function parseSegments(
  content: string,
  citations: SourceCitation[] | undefined
): Segment[] {
  if (!citations || citations.length === 0) {
    return [{ kind: "text", value: content }];
  }
  const byFilename = new Map(citations.map((c) => [c.filename, c]));
  const byLower = new Map(citations.map((c) => [c.filename.toLowerCase(), c]));
  const segments: Segment[] = [];
  const regex = /\[([^[\]\n]+)\]/g;
  let lastIndex = 0;
  for (const match of content.matchAll(regex)) {
    const [fullMatch, inner] = match;
    const citation = byFilename.get(inner) ?? byLower.get(inner.toLowerCase());
    if (!citation) continue;
    const at = match.index ?? 0;
    if (at > lastIndex) {
      segments.push({ kind: "text", value: content.slice(lastIndex, at) });
    }
    segments.push({ kind: "citation", citation });
    lastIndex = at + fullMatch.length;
  }
  if (lastIndex < content.length) {
    segments.push({ kind: "text", value: content.slice(lastIndex) });
  }
  return segments;
}

const sourceDomId = (messageId: string, index: number) =>
  `source-${messageId}-${index}`;

function CitationMarker({
  citation,
  onClick,
}: {
  citation: SourceCitation;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            onClick={onClick}
            className="bg-background/60 hover:bg-accent mx-0.5 inline rounded border px-1 py-0 text-xs font-medium transition-colors"
          >
            {citation.filename}
          </button>
        }
      />
      <TooltipContent side="top" className="max-w-xs">
        <div className="text-xs font-medium">{citation.filename}</div>
        {/* opacity-80, not text-muted-foreground: tooltip uses
            bg-foreground text-background, so muted classes render
            unreadable on the dark bubble. */}
        {citation.section_heading && (
          <div className="mt-0.5 text-xs opacity-80">
            {citation.section_heading}
          </div>
        )}
        <div className="mt-1 line-clamp-3 text-xs opacity-80">
          {citation.text}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function scrollToSource(messageId: string, index: number) {
  const el = document.getElementById(sourceDomId(messageId, index));
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  // Plain classList flash — React state would force a re-render loop
  // during streaming. The flash disappears on the next render or after
  // 1.5s, whichever comes first. Either outcome is harmless.
  el.classList.add("ring-primary", "ring-2");
  setTimeout(() => el.classList.remove("ring-primary", "ring-2"), 1500);
}

export function SearchPage() {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isSearching, setIsSearching] = React.useState(false);
  const [searchResults, setSearchResults] = React.useState<SearchResultItem[]>(
    []
  );
  const [queryTimeMs, setQueryTimeMs] = React.useState<number | null>(null);
  const [hasSearched, setHasSearched] = React.useState(false);

  const [chatMessages, setChatMessages] = React.useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = React.useState("");
  const [isSending, setIsSending] = React.useState(false);
  const [streamingMessageId, setStreamingMessageId] = React.useState<
    string | null
  >(null);
  const chatEndRef = React.useRef<HTMLDivElement>(null);

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

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = chatInput.trim();
    if (!question) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
    };
    const assistantId = crypto.randomUUID();
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
    };

    setChatMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setChatInput("");
    setIsSending(true);
    setStreamingMessageId(assistantId);

    const updateAssistant = (patch: (m: ChatMessage) => ChatMessage) => {
      setChatMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? patch(m) : m))
      );
    };

    try {
      await streamRagAnswer(
        { question, max_chunks: 5 },
        {
          onEvent: (event) => {
            switch (event.event) {
              case "citations":
                updateAssistant((m) => ({ ...m, sources: event.data }));
                break;
              case "delta":
                updateAssistant((m) => ({
                  ...m,
                  content: m.content + event.data,
                }));
                break;
              case "done":
                updateAssistant((m) => ({
                  ...m,
                  model: event.data.model,
                  queryTimeMs: event.data.query_time_ms,
                  confidence: event.data.confidence,
                }));
                break;
              case "error":
                toast.error(event.data.message);
                break;
            }
          },
        }
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Streaming failed");
    } finally {
      setIsSending(false);
      setStreamingMessageId(null);
    }
  };

  React.useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  return (
    <div className="flex h-full flex-col gap-6">
      <div>
        <Typography variant="h3">Search & Q&A</Typography>
        <Typography variant="muted">
          Search documents using natural language or ask questions
        </Typography>
      </div>

      <Tabs
        defaultValue="search"
        className="flex min-h-0 w-full flex-1 flex-col"
      >
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="search">
            <SearchIcon className="mr-2 size-4" />
            Semantic Search
          </TabsTrigger>
          <TabsTrigger value="chat">
            <SparklesIcon className="mr-2 size-4" />
            AI Q&A
          </TabsTrigger>
        </TabsList>

        {/* Semantic Search Tab */}
        <TabsContent value="search" className="mt-6">
          <div className="space-y-6">
            <form onSubmit={handleSearch} className="flex gap-2">
              <div className="relative flex-1">
                <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
                <Input
                  placeholder="Search documents using natural language..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Button type="submit" disabled={isSearching}>
                {isSearching ? "Searching..." : "Search"}
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
                                <Typography
                                  variant="small"
                                  className="font-medium"
                                >
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
                                  (result.metadata as Record<string, unknown>)
                                    .skills
                                ) && (
                                  <div className="mt-2 flex flex-wrap gap-1">
                                    {(
                                      (
                                        result.metadata as Record<
                                          string,
                                          unknown
                                        >
                                      ).skills as string[]
                                    )
                                      .slice(0, 8)
                                      .map((skill: string) => (
                                        <Badge
                                          key={skill}
                                          variant="secondary"
                                          className="text-xs"
                                        >
                                          {skill}
                                        </Badge>
                                      ))}
                                  </div>
                                )}
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            <Badge
                              variant="outline"
                              className={
                                result.confidence === "high"
                                  ? "border-green-500 text-green-700 dark:text-green-400"
                                  : result.confidence === "medium"
                                    ? "border-amber-500 text-amber-700 dark:text-amber-400"
                                    : "border-muted-foreground text-muted-foreground"
                              }
                            >
                              {result.confidence} relevance
                            </Badge>
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
                  Try different keywords or upload more documents
                </Typography>
              </div>
            )}
          </div>
        </TabsContent>

        {/* AI Q&A Tab */}
        <TabsContent value="chat" className="mt-6 flex min-h-0 flex-1 flex-col">
          <Card className="flex h-full min-h-0 flex-col">
            <CardHeader className="border-b p-4">
              <div className="flex items-center gap-2">
                <SparklesIcon className="text-primary size-5" />
                <Typography variant="h5">Ask about your documents</Typography>
              </div>
              <Typography variant="muted" className="text-sm">
                Ask questions and get AI-powered answers with source citations
              </Typography>
            </CardHeader>

            <ScrollArea className="flex-1 p-4">
              <div className="space-y-4">
                {chatMessages.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <SparklesIcon className="text-muted-foreground size-12 opacity-50" />
                    <Typography variant="h5" className="mt-4">
                      Ask anything about your documents
                    </Typography>
                    <Typography variant="muted" className="mt-1">
                      e.g. &ldquo;Who has Kubernetes experience?&rdquo;
                    </Typography>
                  </div>
                )}
                {chatMessages.map((message) => {
                  const isStreaming = message.id === streamingMessageId;
                  const isEmptyStreaming = isStreaming && !message.content;
                  return (
                    <div
                      key={message.id}
                      className={`flex gap-3 ${
                        message.role === "user"
                          ? "justify-end"
                          : "justify-start"
                      }`}
                    >
                      {message.role === "assistant" && (
                        <div className="bg-primary flex size-8 shrink-0 items-center justify-center rounded-full">
                          <BotIcon className="size-4 text-white" />
                        </div>
                      )}
                      <div
                        className={`max-w-[80%] rounded-lg p-3 ${
                          message.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted"
                        }`}
                      >
                        {isEmptyStreaming ? (
                          <div
                            aria-label="Assistant is thinking"
                            className="flex gap-1 py-1"
                          >
                            <span className="bg-foreground/30 size-2 animate-bounce rounded-full" />
                            <span className="bg-foreground/30 size-2 animate-bounce rounded-full [animation-delay:0.1s]" />
                            <span className="bg-foreground/30 size-2 animate-bounce rounded-full [animation-delay:0.2s]" />
                          </div>
                        ) : (
                          <Typography
                            variant="small"
                            className={
                              message.role === "user"
                                ? "text-primary-foreground whitespace-pre-wrap"
                                : "whitespace-pre-wrap"
                            }
                          >
                            {message.role === "assistant"
                              ? parseSegments(
                                  message.content,
                                  message.sources
                                ).map((seg, i) =>
                                  seg.kind === "text" ? (
                                    <React.Fragment key={i}>
                                      {seg.value}
                                    </React.Fragment>
                                  ) : (
                                    <CitationMarker
                                      key={i}
                                      citation={seg.citation}
                                      onClick={() => {
                                        const idx =
                                          message.sources?.findIndex(
                                            (s) =>
                                              s.filename ===
                                                seg.citation.filename &&
                                              s.chunk_index ===
                                                seg.citation.chunk_index
                                          ) ?? -1;
                                        if (idx >= 0)
                                          scrollToSource(message.id, idx);
                                      }}
                                    />
                                  )
                                )
                              : message.content}
                            {isStreaming && (
                              <span
                                aria-hidden
                                className="bg-foreground/60 ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-sm align-baseline"
                              />
                            )}
                          </Typography>
                        )}
                        {message.sources && message.sources.length > 0 && (
                          <>
                            <Separator className="my-2" />
                            <Typography
                              variant="muted"
                              className="mb-1 text-xs"
                            >
                              Sources:
                            </Typography>
                            <div className="space-y-1">
                              {message.sources.map((source, idx) => (
                                <div
                                  key={idx}
                                  id={sourceDomId(message.id, idx)}
                                  className="bg-background/50 rounded p-2 text-xs transition-shadow"
                                >
                                  <div className="flex flex-wrap items-baseline gap-x-2">
                                    <span className="font-medium">
                                      {source.filename}
                                    </span>
                                    {source.section_heading && (
                                      <span className="text-muted-foreground">
                                        · {source.section_heading}
                                      </span>
                                    )}
                                    {source.page_number != null && (
                                      <span className="text-muted-foreground">
                                        · p.{source.page_number}
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-muted-foreground mt-0.5 line-clamp-2">
                                    <HighlightedText
                                      text={source.text}
                                      spans={source.match_spans}
                                    />
                                  </p>
                                </div>
                              ))}
                            </div>
                          </>
                        )}
                        {message.queryTimeMs != null && (
                          <div className="mt-1 flex items-center gap-2">
                            <Typography
                              variant="muted"
                              className="text-xs opacity-60"
                            >
                              {message.model} · {message.queryTimeMs}ms
                            </Typography>
                            {message.confidence && (
                              <Badge
                                variant="outline"
                                className={
                                  message.confidence === "high"
                                    ? "border-green-500 text-green-700 dark:text-green-400"
                                    : message.confidence === "medium"
                                      ? "border-amber-500 text-amber-700 dark:text-amber-400"
                                      : "border-muted-foreground text-muted-foreground"
                                }
                              >
                                {message.confidence} confidence
                              </Badge>
                            )}
                          </div>
                        )}
                      </div>
                      {message.role === "user" && (
                        <div className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-full">
                          <UserIcon className="size-4" />
                        </div>
                      )}
                    </div>
                  );
                })}
                <div ref={chatEndRef} />
              </div>
            </ScrollArea>

            <div className="border-t p-4">
              <form onSubmit={handleSendMessage} className="flex gap-2">
                <Textarea
                  placeholder="Ask a question about your documents..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  className="max-h-32 min-h-[44px] resize-none"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage(e);
                    }
                  }}
                />
                <Button type="submit" disabled={isSending || !chatInput.trim()}>
                  <SendIcon className="size-4" />
                </Button>
              </form>
              <Typography variant="muted" className="mt-2 text-center text-xs">
                Press Enter to send, Shift+Enter for new line
              </Typography>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
