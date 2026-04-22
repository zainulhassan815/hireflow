import { DownloadIcon } from "lucide-react";

import { usePwaInstall } from "@/hooks/use-pwa-install";
import { cn } from "@/lib/utils";

interface InstallAppButtonProps {
  collapsed: boolean;
}

export function InstallAppButton({ collapsed }: InstallAppButtonProps) {
  const { state, promptInstall } = usePwaInstall();

  if (state !== "available") return null;

  return (
    <button
      type="button"
      onClick={() => {
        void promptInstall();
      }}
      className={cn(
        "hover:bg-muted/60 text-muted-foreground hover:text-foreground flex w-full items-center gap-3 p-2 text-left text-sm transition-colors",
        "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
        collapsed && "justify-center"
      )}
      title="Install Hireflow as an app"
    >
      <DownloadIcon className="size-4 shrink-0" />
      {!collapsed && <span className="truncate">Install app</span>}
    </button>
  );
}
