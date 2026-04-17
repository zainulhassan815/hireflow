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
  queryDocuments,
  type SearchResultItem,
  type SourceCitation,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
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
    if (!chatInput.trim()) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: chatInput,
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    setIsSending(true);

    const { data, error } = await queryDocuments({
      body: { question: chatInput, max_chunks: 5 },
    });

    if (error) {
      toast.error(extractApiError(error).message);
      setIsSending(false);
      return;
    }

    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: data?.answer ?? "No answer generated.",
      sources: data?.citations ?? [],
      model: data?.model,
      queryTimeMs: data?.query_time_ms,
    };

    setChatMessages((prev) => [...prev, assistantMessage]);
    setIsSending(false);
  };

  React.useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Typography variant="h3">Search & Q&A</Typography>
        <Typography variant="muted">
          Search documents using natural language or ask questions
        </Typography>
      </div>

      <Tabs defaultValue="search" className="w-full">
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
                                  {result.highlights[0].text}
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
        <TabsContent value="chat" className="mt-6">
          <Card className="flex h-[600px] flex-col">
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
                {chatMessages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex gap-3 ${
                      message.role === "user" ? "justify-end" : "justify-start"
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
                      <Typography
                        variant="small"
                        className={
                          message.role === "user"
                            ? "text-primary-foreground whitespace-pre-wrap"
                            : "whitespace-pre-wrap"
                        }
                      >
                        {message.content}
                      </Typography>
                      {message.sources && message.sources.length > 0 && (
                        <>
                          <Separator className="my-2" />
                          <Typography variant="muted" className="mb-1 text-xs">
                            Sources:
                          </Typography>
                          <div className="space-y-1">
                            {message.sources.map((source, idx) => (
                              <div
                                key={idx}
                                className="bg-background/50 rounded p-2 text-xs"
                              >
                                <span className="font-medium">
                                  {source.filename}
                                </span>
                                <p className="text-muted-foreground mt-0.5 line-clamp-2">
                                  {source.text}
                                </p>
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                      {message.queryTimeMs != null && (
                        <Typography
                          variant="muted"
                          className="mt-1 text-xs opacity-60"
                        >
                          {message.model} · {message.queryTimeMs}ms
                        </Typography>
                      )}
                    </div>
                    {message.role === "user" && (
                      <div className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-full">
                        <UserIcon className="size-4" />
                      </div>
                    )}
                  </div>
                ))}
                {isSending && (
                  <div className="flex gap-3">
                    <div className="bg-primary flex size-8 shrink-0 items-center justify-center rounded-full">
                      <BotIcon className="size-4 text-white" />
                    </div>
                    <div className="bg-muted rounded-lg p-3">
                      <div className="flex gap-1">
                        <span className="bg-foreground/30 size-2 animate-bounce rounded-full" />
                        <span className="bg-foreground/30 size-2 animate-bounce rounded-full [animation-delay:0.1s]" />
                        <span className="bg-foreground/30 size-2 animate-bounce rounded-full [animation-delay:0.2s]" />
                      </div>
                    </div>
                  </div>
                )}
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
