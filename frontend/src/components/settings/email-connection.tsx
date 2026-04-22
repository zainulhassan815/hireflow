import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircleIcon,
  MailIcon,
  PlusIcon,
  RefreshCwIcon,
  UnplugIcon,
} from "lucide-react";
import { toast } from "sonner";

import {
  gmailAuthorizeMutation,
  gmailDisconnectMutation,
  gmailSyncNowMutation,
  listGmailConnectionsOptions,
  listGmailConnectionsQueryKey,
} from "@/api";
import type { GmailConnection } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Typography } from "@/components/ui/typography";

export function EmailConnection() {
  const queryClient = useQueryClient();
  const { data: connections, isLoading } = useQuery({
    ...listGmailConnectionsOptions(),
    // Poll every 15s so last_synced_at updates shortly after a sync
    // completes without requiring the user to refresh. Cheap (one
    // authenticated GET) and only while the card is mounted.
    refetchInterval: 15_000,
  });

  const authorize = useMutation({
    ...gmailAuthorizeMutation(),
    onSuccess: (data) => {
      window.location.href = data.authorize_url;
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: listGmailConnectionsQueryKey() });

  const items = connections ?? [];
  const hasConnections = items.length > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <MailIcon className="size-5" />
          <Typography variant="h5">Gmail Integration</Typography>
        </div>
        <Typography variant="muted">
          Connect one or more Gmail accounts so Hireflow can auto-ingest resume
          attachments and send follow-ups. Each mailbox syncs independently.
        </Typography>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex items-center justify-center rounded-lg border p-6">
            <Spinner className="size-4" />
          </div>
        ) : hasConnections ? (
          <>
            <div className="space-y-2">
              {items.map((connection) => (
                <ConnectionRow
                  key={connection.id}
                  connection={connection}
                  onAfterMutate={invalidate}
                />
              ))}
            </div>
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => authorize.mutate({})}
                disabled={authorize.isPending}
              >
                <PlusIcon className="size-4" data-icon="inline-start" />
                {authorize.isPending
                  ? "Redirecting..."
                  : "Connect another account"}
              </Button>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
            <div className="flex items-center gap-4">
              <div className="bg-muted flex size-12 items-center justify-center rounded-full">
                <MailIcon className="text-muted-foreground size-6" />
              </div>
              <div>
                <Typography variant="small" className="font-medium">
                  Not connected
                </Typography>
                <Typography variant="muted" className="text-sm">
                  Connect your Gmail to start syncing resumes.
                </Typography>
              </div>
            </div>
            <Button
              onClick={() => authorize.mutate({})}
              disabled={authorize.isPending}
            >
              {authorize.isPending ? "Redirecting..." : "Connect Gmail"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ConnectionRow({
  connection,
  onAfterMutate,
}: {
  connection: GmailConnection;
  onAfterMutate: () => void;
}) {
  const syncNow = useMutation({
    ...gmailSyncNowMutation(),
    onSuccess: () => {
      toast.success(
        `Sync started for ${connection.gmail_email} — new resumes will appear shortly`
      );
      onAfterMutate();
    },
  });

  const disconnect = useMutation({
    ...gmailDisconnectMutation(),
    onSuccess: () => {
      toast.success(`Disconnected ${connection.gmail_email}`);
      onAfterMutate();
    },
  });

  const connectedAt = new Date(connection.connected_at);
  const lastSyncedAt = connection.last_synced_at
    ? new Date(connection.last_synced_at)
    : null;

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex size-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
          <MailIcon className="size-6 text-green-600 dark:text-green-400" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Typography variant="small" className="truncate font-medium">
              {connection.gmail_email}
            </Typography>
            <Badge variant="outline" className="gap-1 text-green-600">
              <CheckCircleIcon className="size-3" />
              Connected
            </Badge>
          </div>
          <Typography variant="muted" className="text-sm">
            {`Connected ${connectedAt.toLocaleString()}`}
            {lastSyncedAt
              ? ` · Last synced ${lastSyncedAt.toLocaleString()}`
              : " · Never synced"}
          </Typography>
        </div>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            syncNow.mutate({ path: { connection_id: connection.id } })
          }
          disabled={syncNow.isPending}
        >
          <RefreshCwIcon
            className={`size-4 ${syncNow.isPending ? "animate-spin" : ""}`}
            data-icon="inline-start"
          />
          {syncNow.isPending ? "Syncing..." : "Sync now"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            disconnect.mutate({ path: { connection_id: connection.id } })
          }
          disabled={disconnect.isPending}
          className="text-destructive"
        >
          <UnplugIcon className="size-4" data-icon="inline-start" />
          Disconnect
        </Button>
      </div>
    </div>
  );
}
