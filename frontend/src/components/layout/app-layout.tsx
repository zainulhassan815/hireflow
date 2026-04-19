import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { SearchIcon } from "lucide-react";

import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { AppSidebar } from "./app-sidebar";

const ROUTE_TITLES: Array<{ match: (p: string) => boolean; title: string }> = [
  { match: (p) => p === "/", title: "Dashboard" },
  { match: (p) => p.startsWith("/documents"), title: "Documents" },
  { match: (p) => p.startsWith("/search"), title: "Search" },
  { match: (p) => p.startsWith("/candidates"), title: "Candidates" },
  { match: (p) => p.startsWith("/jobs"), title: "Jobs" },
  { match: (p) => p.startsWith("/logs"), title: "Activity Logs" },
  { match: (p) => p.startsWith("/settings"), title: "Settings" },
];

function getPageTitle(pathname: string): string | null {
  return ROUTE_TITLES.find(({ match }) => match(pathname))?.title ?? null;
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const pageTitle = getPageTitle(location.pathname);
  const onSearchPage = location.pathname.startsWith("/search");

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-3 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          {pageTitle && (
            <>
              <Separator orientation="vertical" className="h-4" />
              <span className="text-foreground text-sm font-medium">
                {pageTitle}
              </span>
            </>
          )}
          {!onSearchPage && (
            <button
              type="button"
              onClick={() => navigate("/search")}
              className="text-muted-foreground hover:text-foreground hover:border-foreground/30 ml-auto flex items-center gap-2 border-b border-transparent py-0.5 text-sm transition-colors"
            >
              <SearchIcon className="size-4" />
              <span>Search…</span>
            </button>
          )}
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
