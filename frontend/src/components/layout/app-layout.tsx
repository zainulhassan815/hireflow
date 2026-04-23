import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useRouteTitle } from "@/hooks/use-document-title";
import { AppSidebar } from "./app-sidebar";
import { CommandPalette } from "./command-palette";

export function AppLayout() {
  useRouteTitle();
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <SidebarProvider>
      <AppSidebar />
      {/* SidebarInset is already a <main> — no need to nest another.
          `min-w-0` is load-bearing: SidebarInset is a flex-row child
          of sidebar-wrapper with `flex-1`, and its default
          `min-width: auto` lets wide content (the F93 Kanban's 5 ×
          288px columns) push it past the viewport and scroll the
          whole page body. Overriding min-width to 0 lets flex-1
          actually constrain the main area; `overflow-auto` scopes
          the scroll inside the main region. */}
      <SidebarInset className="min-w-0 overflow-auto p-6">
        <Outlet />
      </SidebarInset>
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </SidebarProvider>
  );
}
