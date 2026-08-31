/**
 * Conversation sidebar for the chat page.
 *
 * A panel inside the page rather than a second global sidebar — the app
 * already has one for navigation (`layout/app-sidebar.tsx`), and nesting
 * two would leave the reader unsure which one owns the current route.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ArchiveIcon } from "lucide-react";

import {
  type Conversation,
  deleteConversationMutation,
  listConversationsQueryKey,
} from "@/api";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Spinner } from "@/components/ui/spinner";
import { Typography } from "@/components/ui/typography";
import { cn } from "@/lib/utils";

/** Recency buckets, matched against local midnight boundaries. */
function bucketOf(updatedAt: Date): string {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const dayMs = 86_400_000;
  const delta = startOfToday.getTime() - updatedAt.getTime();
  if (delta <= 0) return "Today";
  if (delta <= dayMs) return "Yesterday";
  if (delta <= 6 * dayMs) return "Past week";
  return "Older";
}

const BUCKET_ORDER = ["Today", "Yesterday", "Past week", "Older"];

export function ConversationList({
  conversations,
  isLoading,
  activeId,
}: {
  conversations: Conversation[];
  isLoading: boolean;
  activeId?: string;
}) {
  const queryClient = useQueryClient();
  const archive = useMutation({
    ...deleteConversationMutation(),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: listConversationsQueryKey() }),
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <Spinner className="size-4" />
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <Typography variant="muted" className="px-3 py-6 text-center text-sm">
        No conversations yet.
      </Typography>
    );
  }

  const grouped = new Map<string, Conversation[]>();
  for (const c of conversations) {
    const bucket = bucketOf(new Date(c.updated_at));
    grouped.set(bucket, [...(grouped.get(bucket) ?? []), c]);
  }

  return (
    <ScrollArea className="flex-1">
      <div className="space-y-4 px-2 pb-4">
        {BUCKET_ORDER.filter((b) => grouped.has(b)).map((bucket) => (
          <div key={bucket}>
            <Typography
              variant="muted"
              className="px-2 py-1 text-xs font-medium tracking-wide uppercase"
            >
              {bucket}
            </Typography>
            <ul className="space-y-0.5">
              {grouped.get(bucket)!.map((c) => (
                <li key={c.id} className="group flex items-center gap-1">
                  <Link
                    to={`/chat/${c.id}`}
                    className={cn(
                      "hover:bg-accent min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-sm",
                      c.id === activeId && "bg-accent font-medium"
                    )}
                  >
                    {c.title ?? "New conversation"}
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 shrink-0 opacity-0 group-hover:opacity-100"
                    aria-label={`Archive ${c.title ?? "conversation"}`}
                    onClick={() =>
                      archive.mutate({ path: { conversation_id: c.id } })
                    }
                  >
                    <ArchiveIcon className="size-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
