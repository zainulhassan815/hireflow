import * as React from "react";
import {
  CheckCircleIcon,
  MailIcon,
  RefreshCwIcon,
  UnplugIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Typography } from "@/components/ui/typography";
import { toast } from "sonner";

interface SyncHistoryItem {
  id: string;
  timestamp: Date;
  resumesFound: number;
  status: "success" | "error";
}

export function EmailConnection() {
  const [isConnected, setIsConnected] = React.useState(false);
  const [isConnecting, setIsConnecting] = React.useState(false);
  const [isSyncing, setIsSyncing] = React.useState(false);
  const [connectedEmail, setConnectedEmail] = React.useState<string | null>(
    null
  );
  const [lastSync, setLastSync] = React.useState<Date | null>(null);
  const [syncHistory, setSyncHistory] = React.useState<SyncHistoryItem[]>([
    {
      id: "1",
      timestamp: new Date(Date.now() - 3600000),
      resumesFound: 5,
      status: "success",
    },
    {
      id: "2",
      timestamp: new Date(Date.now() - 7200000),
      resumesFound: 3,
      status: "success",
    },
    {
      id: "3",
      timestamp: new Date(Date.now() - 86400000),
      resumesFound: 0,
      status: "error",
    },
  ]);

  const handleConnect = async () => {
    setIsConnecting(true);
    // Simulate OAuth flow
    await new Promise((resolve) => setTimeout(resolve, 1500));
    setIsConnected(true);
    setConnectedEmail("hr@company.com");
    setLastSync(new Date());
    setIsConnecting(false);
    toast.success("Gmail account connected successfully");
  };

  const handleDisconnect = () => {
    setIsConnected(false);
    setConnectedEmail(null);
    setLastSync(null);
    toast.success("Gmail account disconnected");
  };

  const handleSync = async () => {
    setIsSyncing(true);
    await new Promise((resolve) => setTimeout(resolve, 2000));

    const newSync: SyncHistoryItem = {
      id: crypto.randomUUID(),
      timestamp: new Date(),
      resumesFound: Math.floor(Math.random() * 10),
      status: "success",
    };

    setSyncHistory((prev) => [newSync, ...prev]);
    setLastSync(new Date());
    setIsSyncing(false);
    toast.success(`Synced ${newSync.resumesFound} new resume(s)`);
  };

  const formatRelativeTime = (date: Date) => {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24)
      return `${diffHours} hour${diffHours > 1 ? "s" : ""} ago`;
    return `${diffDays} day${diffDays > 1 ? "s" : ""} ago`;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <MailIcon className="size-5" />
          <Typography variant="h5">Email Integration</Typography>
        </div>
        <Typography variant="muted">
          Connect your Gmail account to automatically sync resume attachments
        </Typography>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Connection Status */}
        <div className="flex items-center justify-between rounded-lg border p-4">
          <div className="flex items-center gap-4">
            <div
              className={`flex size-12 items-center justify-center rounded-full ${
                isConnected ? "bg-green-100 dark:bg-green-900/30" : "bg-muted"
              }`}
            >
              <MailIcon
                className={`size-6 ${
                  isConnected
                    ? "text-green-600 dark:text-green-400"
                    : "text-muted-foreground"
                }`}
              />
            </div>
            <div>
              {isConnected ? (
                <>
                  <div className="flex items-center gap-2">
                    <Typography variant="small" className="font-medium">
                      {connectedEmail}
                    </Typography>
                    <Badge variant="outline" className="gap-1 text-green-600">
                      <CheckCircleIcon className="size-3" />
                      Connected
                    </Badge>
                  </div>
                  <Typography variant="muted" className="text-sm">
                    Last synced:{" "}
                    {lastSync ? formatRelativeTime(lastSync) : "Never"}
                  </Typography>
                </>
              ) : (
                <>
                  <Typography variant="small" className="font-medium">
                    No email connected
                  </Typography>
                  <Typography variant="muted" className="text-sm">
                    Connect your Gmail to start syncing resumes
                  </Typography>
                </>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {isConnected ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSync}
                  disabled={isSyncing}
                >
                  <RefreshCwIcon
                    className={`size-4 ${isSyncing ? "animate-spin" : ""}`}
                    data-icon="inline-start"
                  />
                  {isSyncing ? "Syncing..." : "Sync Now"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDisconnect}
                  className="text-destructive"
                >
                  <UnplugIcon className="size-4" data-icon="inline-start" />
                  Disconnect
                </Button>
              </>
            ) : (
              <Button onClick={handleConnect} disabled={isConnecting}>
                {isConnecting ? "Connecting..." : "Connect Gmail"}
              </Button>
            )}
          </div>
        </div>

        {/* Sync History */}
        {isConnected && syncHistory.length > 0 && (
          <>
            <Separator />
            <div>
              <Typography variant="h6" className="mb-3">
                Sync History
              </Typography>
              <div className="space-y-2">
                {syncHistory.slice(0, 5).map((item) => (
                  <div
                    key={item.id}
                    className="bg-muted/50 flex items-center justify-between rounded-lg p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`size-2 rounded-full ${
                          item.status === "success"
                            ? "bg-green-500"
                            : "bg-red-500"
                        }`}
                      />
                      <div>
                        <Typography variant="small">
                          {item.status === "success"
                            ? `${item.resumesFound} resume${item.resumesFound !== 1 ? "s" : ""} synced`
                            : "Sync failed"}
                        </Typography>
                        <Typography variant="muted" className="text-xs">
                          {formatRelativeTime(item.timestamp)}
                        </Typography>
                      </div>
                    </div>
                    <Badge
                      variant={
                        item.status === "success" ? "outline" : "destructive"
                      }
                    >
                      {item.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {/* Help Text */}
        <div className="bg-muted/50 rounded-lg p-4">
          <Typography variant="small" className="font-medium">
            How it works
          </Typography>
          <ul className="text-muted-foreground mt-2 space-y-1 text-sm">
            <li>
              • Connect your Gmail account using OAuth (secure, no password
              stored)
            </li>
            <li>• The system scans incoming emails for resume attachments</li>
            <li>• Resumes are automatically extracted and processed</li>
            <li>
              • You can trigger manual sync anytime or set up automatic sync
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
