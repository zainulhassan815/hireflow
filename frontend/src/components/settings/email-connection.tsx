import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircleIcon,
  HistoryIcon,
  MailIcon,
  PlusIcon,
  RefreshCwIcon,
  UnplugIcon,
} from "lucide-react";
import { toast } from "sonner";

import {
  gmailAuthorizeMutation,
  gmailBackfillMutation,
  gmailDisconnectMutation,
  gmailSyncNowMutation,
  listGmailConnectionsOptions,
  listGmailConnectionsQueryKey,
  updateGmailConnectionMutation,
} from "@/api";
import type { GmailConnection } from "@/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
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
          attachments. Read-only access; each mailbox syncs independently.
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
  const backfillBefore = connection.backfill_before
    ? new Date(connection.backfill_before)
    : null;
  const backfillUntil = connection.backfill_until
    ? new Date(connection.backfill_until)
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
          {backfillBefore ? (
            <Typography variant="muted" className="text-sm">
              {`Backfilling — reached ${backfillBefore.toLocaleDateString()}`}
              {backfillUntil ? ` of ${backfillUntil.toLocaleDateString()}` : ""}
            </Typography>
          ) : null}
          <MirrorDeletionsToggle
            connection={connection}
            onAfterMutate={onAfterMutate}
          />
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
        <BackfillDialog
          connection={connection}
          isRunning={backfillBefore !== null}
          onAfterMutate={onAfterMutate}
        />
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

function BackfillDialog({
  connection,
  isRunning,
  onAfterMutate,
}: {
  connection: GmailConnection;
  isRunning: boolean;
  onAfterMutate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [until, setUntil] = useState("");
  const untilId = useId();

  const backfill = useMutation({
    ...gmailBackfillMutation(),
    onSuccess: () => {
      toast.success(
        `Backfill started for ${connection.gmail_email} — older resumes arrive a batch at a time`
      );
      setOpen(false);
      onAfterMutate();
    },
    onError: () =>
      toast.error("Could not start the backfill. Pick a past date."),
  });

  // Native max: the API rejects today or later, so don't offer it.
  // Lazy state rather than a render-body call — reading the clock during
  // render is impure and the value only needs to be right on mount.
  const [yesterday] = useState(() =>
    new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={isRunning}
      >
        <HistoryIcon className="size-4" data-icon="inline-start" />
        {isRunning ? "Backfilling..." : "Backfill"}
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Backfill older mail</DialogTitle>
          <DialogDescription>
            Pull resume attachments from {connection.gmail_email} going back to
            the date you choose. Hireflow works backwards a batch at a time on
            the regular sync schedule, so new mail keeps arriving meanwhile.
          </DialogDescription>
        </DialogHeader>
        <Field>
          <FieldLabel htmlFor={untilId}>Go back to</FieldLabel>
          <Input
            id={untilId}
            type="date"
            max={yesterday}
            value={until}
            onChange={(e) => setUntil(e.target.value)}
          />
        </Field>
        <DialogFooter>
          <DialogClose
            render={
              <Button variant="ghost" size="sm">
                Cancel
              </Button>
            }
          />
          <Button
            size="sm"
            disabled={!until || backfill.isPending}
            onClick={() =>
              backfill.mutate({
                path: { connection_id: connection.id },
                // The generated client types this as Date; a date-only
                // string parses as UTC midnight, so no off-by-one.
                body: { until: new Date(until) },
              })
            }
          >
            {backfill.isPending ? "Starting..." : "Start backfill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MirrorDeletionsToggle({
  connection,
  onAfterMutate,
}: {
  connection: GmailConnection;
  onAfterMutate: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const switchId = useId();

  const update = useMutation({
    ...updateGmailConnectionMutation(),
    onSuccess: (updated) => {
      toast.success(
        updated.mirror_deletions
          ? `Deletions from ${connection.gmail_email} will now remove matching documents`
          : `Deletion mirroring off for ${connection.gmail_email}`
      );
      setConfirming(false);
      onAfterMutate();
    },
    onError: () => toast.error("Could not change the setting."),
  });

  const apply = (mirror_deletions: boolean) =>
    update.mutate({
      path: { connection_id: connection.id },
      body: { mirror_deletions },
    });

  return (
    <>
      <div className="mt-2 flex items-center gap-2">
        <Switch
          id={switchId}
          checked={connection.mirror_deletions}
          disabled={update.isPending}
          // Turning it on is destructive, so it asks first. Turning it
          // off is safe and applies immediately.
          onCheckedChange={(next) =>
            next ? setConfirming(true) : apply(false)
          }
        />
        <label htmlFor={switchId} className="text-muted-foreground text-sm">
          Delete documents when their email is permanently deleted (emptied from
          Trash) — moving mail to Trash alone never deletes anything
        </label>
      </div>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mirror deletions from Gmail?</AlertDialogTitle>
            <AlertDialogDescription>
              Moving an email to Trash will <strong>not</strong> delete anything
              — Hireflow only marks it, and unmarks it if you restore the
              message. Deletion happens only when the email is{" "}
              <strong>permanently</strong> gone from {connection.gmail_email}:
              emptied from Trash by hand, or purged automatically by Gmail after
              30 days. At that point Hireflow deletes every document it took
              from that email, along with the stored file, its search results,
              and its link to any candidate. That cannot be undone, and
              re-syncing will not bring them back.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel render={<Button variant="ghost" size="sm" />}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              render={<Button variant="destructive" size="sm" />}
              onClick={() => apply(true)}
              disabled={update.isPending}
            >
              {update.isPending ? "Enabling..." : "Enable"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
