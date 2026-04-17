import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircleIcon, MailIcon, UnplugIcon } from "lucide-react";
import { toast } from "sonner";

import {
  gmailAuthorizeMutation,
  gmailDisconnectMutation,
  gmailStatusOptions,
  gmailStatusQueryKey,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Typography } from "@/components/ui/typography";

export function EmailConnection() {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery(gmailStatusOptions());

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
                    {lastSyncedAt &&
                      ` · Last synced ${lastSyncedAt.toLocaleString()}`}
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
          <div className="shrink-0">
            {connected ? (
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
