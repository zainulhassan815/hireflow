import * as React from "react";
import {
  ArrowUpIcon,
  ChevronDownIcon,
  PlusIcon,
  SparklesIcon,
  SquareIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import type { SourceCitation } from "@/api";
import { streamRagAnswer, type Intent } from "@/api/rag-stream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HighlightedText } from "@/components/highlighted-text";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Typography } from "@/components/ui/typography";
import { Logo } from "@/components/ui/logo";
import { cn } from "@/lib/utils";

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

const SUGGESTED_PROMPTS = [
  {
    title: "Find specialists",
    prompt: "Who has Kubernetes experience?",
  },
  {
    title: "Compare candidates",
    prompt: "Compare the top three backend candidates by years of experience.",
  },
  {
    title: "Filter by clearance",
    prompt: "Which resumes mention an active security clearance?",
  },
  {
    title: "Summarize a role",
    prompt: "Summarize the responsibilities of the senior data engineer role.",
  },
];

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  model?: string;
  queryTimeMs?: number;
  confidence?: "high" | "medium" | "low" | null;
  intent?: Intent;
}

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
  `qa-source-${messageId}-${index}`;

function scrollToSource(messageId: string, index: number) {
  const el = document.getElementById(sourceDomId(messageId, index));
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("ring-primary", "ring-2");
  setTimeout(() => el.classList.remove("ring-primary", "ring-2"), 1500);
}

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
            className="bg-muted/60 hover:bg-accent hover:text-accent-foreground mx-0.5 inline rounded border px-1 py-0 text-xs font-medium transition-colors"
          >
            {citation.filename}
          </button>
        }
      />
      <TooltipContent side="top" className="max-w-xs">
        <div className="text-xs font-medium">{citation.filename}</div>
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

function renderWithCitations(
  children: React.ReactNode,
  sources: SourceCitation[] | undefined,
  messageId: string
): React.ReactNode {
  return React.Children.map(children, (child, i) => {
    if (typeof child !== "string") return child;
    return parseSegments(child, sources).map((seg, j) =>
      seg.kind === "text" ? (
        <React.Fragment key={`${i}-${j}`}>{seg.value}</React.Fragment>
      ) : (
        <CitationMarker
          key={`${i}-${j}`}
          citation={seg.citation}
          onClick={() => {
            const idx =
              sources?.findIndex(
                (s) =>
                  s.filename === seg.citation.filename &&
                  s.chunk_index === seg.citation.chunk_index
              ) ?? -1;
            if (idx >= 0) scrollToSource(messageId, idx);
          }}
        />
      )
    );
  });
}

function AssistantMarkdown({
  content,
  sources,
  messageId,
  isStreaming,
}: {
  content: string;
  sources?: SourceCitation[];
  messageId: string;
  isStreaming: boolean;
}) {
  const components = React.useMemo(
    () => ({
      p: ({ children }: { children?: React.ReactNode }) => (
        <p className="mb-3 leading-7 last:mb-0">
          {renderWithCitations(children, sources, messageId)}
        </p>
      ),
      li: ({ children }: { children?: React.ReactNode }) => (
        <li className="leading-7">
          {renderWithCitations(children, sources, messageId)}
        </li>
      ),
      td: ({ children }: { children?: React.ReactNode }) => (
        <td className="border px-3 py-2">
          {renderWithCitations(children, sources, messageId)}
        </td>
      ),
      th: ({ children }: { children?: React.ReactNode }) => (
        <th className="bg-muted/40 border px-3 py-2 text-left font-semibold">
          {children}
        </th>
      ),
      table: ({ children }: { children?: React.ReactNode }) => (
        <div className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-sm">{children}</table>
        </div>
      ),
      ul: ({ children }: { children?: React.ReactNode }) => (
        <ul className="mb-3 ml-5 list-disc space-y-1 last:mb-0">{children}</ul>
      ),
      ol: ({ children }: { children?: React.ReactNode }) => (
        <ol className="mb-3 ml-5 list-decimal space-y-1 last:mb-0">
          {children}
        </ol>
      ),
      h1: ({ children }: { children?: React.ReactNode }) => (
        <h1 className="font-display mt-4 mb-2 text-xl font-semibold">
          {children}
        </h1>
      ),
      h2: ({ children }: { children?: React.ReactNode }) => (
        <h2 className="font-display mt-4 mb-2 text-lg font-semibold">
          {children}
        </h2>
      ),
      h3: ({ children }: { children?: React.ReactNode }) => (
        <h3 className="mt-3 mb-1.5 text-base font-semibold">{children}</h3>
      ),
      code: ({ children }: { children?: React.ReactNode }) => (
        <code className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]">
          {children}
        </code>
      ),
      pre: ({ children }: { children?: React.ReactNode }) => (
        <pre className="bg-muted my-3 overflow-x-auto rounded p-3 font-mono text-xs">
          {children}
        </pre>
      ),
      blockquote: ({ children }: { children?: React.ReactNode }) => (
        <blockquote className="border-muted-foreground/40 text-muted-foreground my-3 border-l-2 pl-3 italic">
          {children}
        </blockquote>
      ),
    }),
    [sources, messageId]
  );

  return (
    <div className="text-foreground text-[15px]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span
          aria-hidden
          className="bg-foreground/70 ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-sm align-baseline"
        />
      )}
    </div>
  );
}

function ThinkingDots() {
  return (
    <div
      aria-label="Assistant is thinking"
      className="flex items-center gap-1.5 py-2"
    >
      <span className="bg-muted-foreground/50 size-2 animate-pulse rounded-full" />
      <span className="bg-muted-foreground/50 size-2 animate-pulse rounded-full [animation-delay:150ms]" />
      <span className="bg-muted-foreground/50 size-2 animate-pulse rounded-full [animation-delay:300ms]" />
    </div>
  );
}

function SourcesPanel({ message }: { message: ChatMessage }) {
  const [open, setOpen] = React.useState(false);
  const sources = message.sources ?? [];
  if (sources.length === 0) return null;

  return (
    <div className="mt-4 rounded border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="hover:bg-muted/40 flex w-full items-center justify-between gap-2 rounded px-3 py-2 text-left text-xs font-medium transition-colors"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <span>Sources</span>
          <span className="text-muted-foreground">({sources.length})</span>
        </span>
        <ChevronDownIcon
          className={cn(
            "text-muted-foreground size-4 transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <div className="space-y-2 border-t p-3">
          {sources.map((source, idx) => (
            <div
              key={idx}
              id={sourceDomId(message.id, idx)}
              className="bg-muted/40 rounded p-2.5 text-xs transition-shadow"
            >
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{source.filename}</span>
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
              <p className="text-muted-foreground mt-1 line-clamp-3 leading-relaxed">
                <HighlightedText
                  text={source.text}
                  spans={source.match_spans}
                />
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageMeta({ message }: { message: ChatMessage }) {
  if (message.queryTimeMs == null) return null;
  return (
    <div className="text-muted-foreground mt-3 flex items-center gap-2 text-xs">
      <span>
        {message.model}
        {" · "}
        {message.queryTimeMs}ms
      </span>
      {message.confidence && CONFIDENCE_DISPLAY[message.confidence] && (
        <Tooltip>
          <TooltipTrigger
            render={
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px]",
                  CONFIDENCE_DISPLAY[message.confidence].className
                )}
              >
                {CONFIDENCE_DISPLAY[message.confidence].label}
              </Badge>
            }
          />
          <TooltipContent>
            {CONFIDENCE_DISPLAY[message.confidence].tooltip}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-[15px] whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({
  message,
  isStreaming,
}: {
  message: ChatMessage;
  isStreaming: boolean;
}) {
  const isEmpty = isStreaming && !message.content;
  return (
    <div className="flex gap-3">
      <div className="bg-foreground text-background font-display mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
        H
      </div>
      <div className="min-w-0 flex-1">
        {isEmpty ? (
          <ThinkingDots />
        ) : (
          <AssistantMarkdown
            content={message.content}
            sources={message.sources}
            messageId={message.id}
            isStreaming={isStreaming}
          />
        )}
        <SourcesPanel message={message} />
        <MessageMeta message={message} />
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  isSending,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  isSending: boolean;
  disabled: boolean;
}) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isSending && value.trim()) onSubmit();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-3 pb-4 sm:px-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!isSending && value.trim()) onSubmit();
        }}
        className="border-input bg-card focus-within:border-ring focus-within:ring-ring/30 flex w-full items-end gap-2 rounded-2xl border p-2 shadow-sm transition-shadow focus-within:ring-2"
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your documents…"
          disabled={disabled}
          rows={1}
          className="placeholder:text-muted-foreground max-h-48 min-h-[40px] flex-1 resize-none border-0 bg-transparent px-3 py-2 text-[15px] outline-none disabled:opacity-50"
        />
        {isSending ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            onClick={onStop}
            aria-label="Stop generating"
            className="shrink-0 rounded-full"
          >
            <SquareIcon className="size-4 fill-current" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={!value.trim() || disabled}
            aria-label="Send message"
            className="shrink-0 rounded-full"
          >
            <ArrowUpIcon className="size-4" />
          </Button>
        )}
      </form>
      <Typography variant="muted" className="mt-2 text-center text-xs">
        Answers come from your library. Press Enter to send, Shift+Enter for a
        new line.
      </Typography>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <div className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-2xl">
        <Logo className="size-7" />
      </div>
      <div className="space-y-2">
        <Typography variant="h3" className="font-display">
          Ask Hireflow
        </Typography>
        <Typography variant="muted">
          Ask anything about your documents. Answers cite the source files they
          came from.
        </Typography>
      </div>
      <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTED_PROMPTS.map((p) => (
          <button
            key={p.prompt}
            type="button"
            onClick={() => onPick(p.prompt)}
            className="hover:border-ring hover:bg-muted/40 group rounded-xl border p-3 text-left transition-colors"
          >
            <div className="flex items-start gap-2">
              <SparklesIcon className="text-muted-foreground group-hover:text-foreground mt-0.5 size-3.5 shrink-0 transition-colors" />
              <div className="flex-1">
                <div className="text-sm font-medium">{p.title}</div>
                <div className="text-muted-foreground mt-0.5 text-xs">
                  {p.prompt}
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export function QaPage() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [isSending, setIsSending] = React.useState(false);
  const [streamingMessageId, setStreamingMessageId] = React.useState<
    string | null
  >(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const isEmpty = messages.length === 0;

  const scrollToBottom = React.useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  React.useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  React.useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const ask = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || isSending) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };
    const assistantId = crypto.randomUUID();
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setInput("");
    setIsSending(true);
    setStreamingMessageId(assistantId);

    const controller = new AbortController();
    abortRef.current = controller;

    const updateAssistant = (patch: (m: ChatMessage) => ChatMessage) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? patch(m) : m))
      );
    };

    try {
      await streamRagAnswer(
        { question: trimmed, max_chunks: 5 },
        {
          signal: controller.signal,
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
                  intent: event.data.intent,
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
      if ((err as Error).name === "AbortError") {
        updateAssistant((m) => ({
          ...m,
          content: m.content || "_Stopped._",
        }));
      } else {
        toast.error(err instanceof Error ? err.message : "Streaming failed");
      }
    } finally {
      setIsSending(false);
      setStreamingMessageId(null);
      abortRef.current = null;
    }
  };

  const stop = () => {
    abortRef.current?.abort();
  };

  const newChat = () => {
    if (isSending) abortRef.current?.abort();
    setMessages([]);
    setInput("");
  };

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border">
      <header className="flex items-center justify-between gap-3 border-b px-6 py-3">
        <div className="min-w-0">
          <Typography variant="h5" className="font-display truncate">
            Ask Hireflow
          </Typography>
          <Typography variant="muted" className="truncate text-xs">
            Conversational Q&amp;A grounded in your library.
          </Typography>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={newChat}
          disabled={isEmpty && !isSending}
        >
          <PlusIcon className="size-4" data-icon="inline-start" />
          New chat
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState onPick={(p) => ask(p)} />
          </div>
        ) : (
          <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-8 sm:px-6">
            {messages.map((message) =>
              message.role === "user" ? (
                <UserMessage key={message.id} content={message.content} />
              ) : (
                <AssistantMessage
                  key={message.id}
                  message={message}
                  isStreaming={message.id === streamingMessageId}
                />
              )
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="bg-muted/20 border-t">
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => ask(input)}
          onStop={stop}
          isSending={isSending}
          disabled={false}
        />
      </div>
    </div>
  );
}
