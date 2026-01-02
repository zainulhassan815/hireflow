import * as React from "react";
import {
  BotIcon,
  DownloadIcon,
  FileTextIcon,
  SearchIcon,
  SendIcon,
  SparklesIcon,
  UserIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Typography } from "@/components/ui/typography";
import { toast } from "sonner";

interface SearchResult {
  id: string;
  documentName: string;
  documentType: string;
  snippet: string;
  relevanceScore: number;
  matchedKeywords: string[];
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { documentName: string; snippet: string }[];
  timestamp: Date;
}

const mockSearchResults: SearchResult[] = [
  {
    id: "1",
    documentName: "John_Doe_Resume.pdf",
    documentType: "resume",
    snippet:
      "...5+ years of experience in **React**, **Node.js**, and **Python**. Led development of scalable microservices architecture...",
    relevanceScore: 95,
    matchedKeywords: ["React", "Node.js", "Python"],
  },
  {
    id: "2",
    documentName: "Sarah_Smith_CV.pdf",
    documentType: "resume",
    snippet:
      "...Senior Frontend Developer with expertise in **React**, TypeScript, and modern web technologies. Experience with large-scale applications...",
    relevanceScore: 88,
    matchedKeywords: ["React", "TypeScript"],
  },
  {
    id: "3",
    documentName: "Q4_Financial_Report.pdf",
    documentType: "report",
    snippet:
      "...The engineering team expanded significantly, with focus on **React** and **Node.js** technologies for the new platform...",
    relevanceScore: 72,
    matchedKeywords: ["React", "Node.js"],
  },
  {
    id: "4",
    documentName: "Technical_Requirements.docx",
    documentType: "other",
    snippet:
      "...Preferred stack includes **React** for frontend, **Node.js** or **Python** for backend services...",
    relevanceScore: 65,
    matchedKeywords: ["React", "Node.js", "Python"],
  },
];

const mockChatHistory: ChatMessage[] = [
  {
    id: "1",
    role: "user",
    content: "Find candidates with React and Node.js experience",
    timestamp: new Date(Date.now() - 60000),
  },
  {
    id: "2",
    role: "assistant",
    content:
      "I found 2 candidates matching your criteria:\n\n1. **John Doe** - 5+ years experience with React, Node.js, and Python. Strong background in microservices.\n\n2. **Sarah Smith** - Senior Frontend Developer specializing in React and TypeScript.",
    sources: [
      {
        documentName: "John_Doe_Resume.pdf",
        snippet: "5+ years experience in React, Node.js, and Python...",
      },
      {
        documentName: "Sarah_Smith_CV.pdf",
        snippet: "Senior Frontend Developer with expertise in React...",
      },
    ],
    timestamp: new Date(Date.now() - 55000),
  },
];

export function SearchPage() {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isSearching, setIsSearching] = React.useState(false);
  const [searchResults, setSearchResults] = React.useState<SearchResult[]>([]);
  const [chatMessages, setChatMessages] =
    React.useState<ChatMessage[]>(mockChatHistory);
  const [chatInput, setChatInput] = React.useState("");
  const [isSending, setIsSending] = React.useState(false);
  const chatEndRef = React.useRef<HTMLDivElement>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    // Simulate search delay
    await new Promise((resolve) => setTimeout(resolve, 800));
    setSearchResults(mockSearchResults);
    setIsSearching(false);
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: chatInput,
      timestamp: new Date(),
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setChatInput("");
    setIsSending(true);

    // Simulate AI response
    await new Promise((resolve) => setTimeout(resolve, 1500));

    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content:
        "Based on my analysis of your documents, I found relevant information that matches your query. The documents contain detailed information about the topics you mentioned.",
      sources: [
        {
          documentName: "Sample_Document.pdf",
          snippet: "Relevant excerpt from the document...",
        },
      ],
      timestamp: new Date(),
    };

    setChatMessages((prev) => [...prev, assistantMessage]);
    setIsSending(false);
  };

  React.useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const handleExport = () => {
    toast.success("Search results exported to Excel");
  };

  const highlightKeywords = (text: string) => {
    return text.replace(
      /\*\*(.*?)\*\*/g,
      '<mark class="bg-yellow-200 dark:bg-yellow-900 px-0.5 rounded">$1</mark>'
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <Typography variant="h3">Search & RAG</Typography>
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
            {/* Search Form */}
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

            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <Typography variant="h5">
                    {searchResults.length} Results Found
                  </Typography>
                  <Button variant="outline" size="sm" onClick={handleExport}>
                    <DownloadIcon className="size-4" data-icon="inline-start" />
                    Export to Excel
                  </Button>
                </div>

                <div className="space-y-3">
                  {searchResults.map((result) => (
                    <Card key={result.id}>
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
                                  {result.documentName}
                                </Typography>
                                <Badge variant="outline" className="text-xs">
                                  {result.documentType}
                                </Badge>
                              </div>
                              <Typography
                                variant="muted"
                                className="mt-1 text-sm"
                                dangerouslySetInnerHTML={{
                                  __html: highlightKeywords(result.snippet),
                                }}
                              />
                              <div className="mt-2 flex flex-wrap gap-1">
                                {result.matchedKeywords.map((keyword) => (
                                  <Badge
                                    key={keyword}
                                    variant="secondary"
                                    className="text-xs"
                                  >
                                    {keyword}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            <div className="flex items-center gap-2">
                              <Progress
                                value={result.relevanceScore}
                                className="h-2 w-16"
                              />
                              <Typography
                                variant="small"
                                className="font-medium"
                              >
                                {result.relevanceScore}%
                              </Typography>
                            </div>
                            <Typography variant="muted" className="text-xs">
                              Relevance
                            </Typography>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {searchResults.length === 0 && searchQuery && !isSearching && (
              <div className="py-12 text-center">
                <SearchIcon className="text-muted-foreground mx-auto size-12 opacity-50" />
                <Typography variant="h5" className="mt-4">
                  No results found
                </Typography>
                <Typography variant="muted" className="mt-1">
                  Try different keywords or phrases
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
                Ask questions and get AI-powered answers based on your document
                collection
              </Typography>
            </CardHeader>

            {/* Chat Messages */}
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-4">
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
                            ? "text-primary-foreground"
                            : ""
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
                                  {source.documentName}
                                </span>
                                <p className="text-muted-foreground mt-0.5">
                                  {source.snippet}
                                </p>
                              </div>
                            ))}
                          </div>
                        </>
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
                        <span className="bg-foreground/30 size-2 animate-bounce rounded-full"></span>
                        <span className="bg-foreground/30 size-2 animate-bounce rounded-full [animation-delay:0.1s]"></span>
                        <span className="bg-foreground/30 size-2 animate-bounce rounded-full [animation-delay:0.2s]"></span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            </ScrollArea>

            {/* Chat Input */}
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
