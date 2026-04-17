import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircleIcon,
  MailIcon,
  RefreshCwIcon,
  UnplugIcon,
} from "lucide-react";
import { toast } from "sonner";

import {
  gmailAuthorizeMutation,
  gmailDisconnectMutation,
  gmailStatusOptions,
  gmailStatusQueryKey,
  gmailSyncNowMutation,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Typography } from "@/components/ui/typography";

export function EmailConnection() {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery({
    ...gmailStatusOptions(),
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

  const disconnect = useMutation({
    ...gmailDisconnectMutation(),
    onSuccess: () => {
      toast.success("Gmail disconnected");
      queryClient.invalidateQueries({ queryKey: gmailStatusQueryKey() });
    },
  });

  const syncNow = useMutation({
    ...gmailSyncNowMutation(),
    onSuccess: () => {
      toast.success("Sync started — new resumes will appear shortly");
      queryClient.invalidateQueries({ queryKey: gmailStatusQueryKey() });
    },
  });

  const connected = status?.connected ?? false;
  const connectedAt = status?.connected_at
    ? new Date(status.connected_at)
    : null;
  const lastSyncedAt = status?.last_synced_at
    ? new Date(status.last_synced_at)
    : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <MailIcon className="size-5" />
          <Typography variant="h5">Gmail Integration</Typography>
        </div>
        <Typography variant="muted">
          Connect Gmail so Hireflow can auto-ingest resume attachments and send
          follow-ups.
        </Typography>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
          <div className="flex items-center gap-4">
            <div
              className={`flex size-12 items-center justify-center rounded-full ${
                connected ? "bg-green-100 dark:bg-green-900/30" : "bg-muted"
              }`}
            >
              <MailIcon
                className={`size-6 ${
                  connected
                    ? "text-green-600 dark:text-green-400"
                    : "text-muted-foreground"
                }`}
              />
            </div>
            <div className="min-w-0">
              {isLoading ? (
                <Spinner className="size-4" />
              ) : connected ? (
                <>
                  <div className="flex items-center gap-2">
                    <Typography
                      variant="small"
                      className="truncate font-medium"
                    >
                      {status?.gmail_email}
                    </Typography>
                    <Badge variant="outline" className="gap-1 text-green-600">
                      <CheckCircleIcon className="size-3" />
                      Connected
                    </Badge>
                  </div>
                  <Typography variant="muted" className="text-sm">
                    {connectedAt && `Connected ${connectedAt.toLocaleString()}`}
                    {lastSyncedAt
                      ? ` · Last synced ${lastSyncedAt.toLocaleString()}`
                      : " · Never synced"}
                  </Typography>
                </>
              ) : (
                <>
                  <Typography variant="small" className="font-medium">
                    Not connected
                  </Typography>
                  <Typography variant="muted" className="text-sm">
                    Connect your Gmail to start syncing resumes.
                  </Typography>
                </>
              )}
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            {connected ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => syncNow.mutate({})}
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
                  onClick={() => disconnect.mutate({})}
                  disabled={disconnect.isPending}
                  className="text-destructive"
                >
                  <UnplugIcon className="size-4" data-icon="inline-start" />
                  Disconnect
                </Button>
              </>
            ) : (
              <Button
                onClick={() => authorize.mutate({})}
                disabled={authorize.isPending}
              >
                {authorize.isPending ? "Redirecting..." : "Connect Gmail"}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
