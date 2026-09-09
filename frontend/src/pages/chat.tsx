/**
 * Persistent chat (F96).
 *
 * Two columns: a conversation list and the active thread. Unlike the
 * legacy `/qa` view, turns are stored server-side, so a reload restores
 * the thread and the model sees prior turns — follow-ups like "what
 * about her Python experience?" resolve against the conversation.
 *
 * The conversation is created lazily on the first message, so opening
 * "New chat" and walking away leaves nothing behind.
 */

import * as React from "react";
import { useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquarePlusIcon } from "lucide-react";
import { toast } from "sonner";

import {
  createConversationMutation,
  listConversationsOptions,
  listConversationsQueryKey,
  listMessagesOptions,
} from "@/api";
import { streamConversationAnswer } from "@/api/rag-stream";
import {
  AssistantMessage,
  type ChatMessage,
  Composer,
  EmptyState,
  UserMessage,
} from "@/components/chat/chat-parts";
import { ConversationList } from "@/components/chat/conversation-list";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

export function ChatPage() {
  const { id: routeId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [isSending, setIsSending] = React.useState(false);
  const [streamingMessageId, setStreamingMessageId] = React.useState<
    string | null
  >(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const conversations = useQuery(listConversationsOptions());
  const history = useQuery({
    ...listMessagesOptions({ path: { conversation_id: routeId ?? "" } }),
    enabled: Boolean(routeId),
  });

  const createConversation = useMutation(createConversationMutation());

  // Hydrate the thread from the server whenever the route changes, so a
  // direct link or a reload lands on the full conversation.
  React.useEffect(() => {
    if (!routeId) {
      setMessages([]);
      return;
    }
    if (!history.data) return;
    setMessages(
      history.data.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
        sources: m.citations ?? undefined,
        model: m.model ?? undefined,
        confidence: m.confidence as ChatMessage["confidence"],
        intent: m.intent as ChatMessage["intent"],
      }))
    );
  }, [routeId, history.data]);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const ask = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || isSending) return;

    let conversationId = routeId;
    if (!conversationId) {
      try {
        const created = await createConversation.mutateAsync({});
        conversationId = created.id;
        // replace, not push: "new chat" shouldn't leave a dead entry in
        // the back stack once it has an id.
        navigate(`/chat/${created.id}`, { replace: true });
      } catch {
        toast.error("Could not start the conversation.");
        return;
      }
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantId, role: "assistant", content: "" },
    ]);
    setInput("");
    setIsSending(true);
    setStreamingMessageId(assistantId);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamConversationAnswer(
        conversationId,
        { question: trimmed, max_chunks: 5 },
        {
          signal: controller.signal,
          onEvent: (event) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                switch (event.event) {
                  case "delta":
                    return { ...m, content: m.content + event.data };
                  case "citations":
                    return { ...m, sources: event.data };
                  case "done":
                    return {
                      ...m,
                      model: event.data.model,
                      queryTimeMs: event.data.query_time_ms,
                      confidence: event.data.confidence,
                      intent: event.data.intent,
                    };
                  case "error":
                    return { ...m, content: event.data.message };
                }
              })
            );
          },
        }
      );
    } catch {
      toast.error("The answer stream failed. Please try again.");
    } finally {
      setIsSending(false);
      setStreamingMessageId(null);
      abortRef.current = null;
      // The title is written server-side after the first exchange, so
      // refresh the list to pick it up.
      queryClient.invalidateQueries({ queryKey: listConversationsQueryKey() });
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div data-full-bleed className="flex h-full min-h-0">
      <aside className="hidden w-64 shrink-0 flex-col border-r md:flex">
        <div className="p-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => navigate("/chat")}
          >
            <MessageSquarePlusIcon
              className="size-4"
              data-icon="inline-start"
            />
            New chat
          </Button>
        </div>
        <ConversationList
          conversations={conversations.data ?? []}
          isLoading={conversations.isLoading}
          activeId={routeId}
        />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        {routeId && history.isLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <Spinner className="size-5" />
          </div>
        ) : isEmpty ? (
          <div className="flex flex-1 items-center justify-center overflow-y-auto">
            <EmptyState onPick={ask} />
          </div>
        ) : (
          <div className="flex-1 space-y-6 overflow-y-auto px-4 py-6">
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
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => ask(input)}
          onStop={() => abortRef.current?.abort()}
          isSending={isSending}
          disabled={isSending}
        />
      </main>
    </div>
  );
}
