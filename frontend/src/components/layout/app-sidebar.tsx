import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  BriefcaseIcon,
  ChevronRightIcon,
  ClipboardListIcon,
  FileTextIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  UsersIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuth } from "@/providers/use-auth";
import { cn } from "@/lib/utils";

const mainNavItems = [
  {
    title: "Dashboard",
    href: "/",
    icon: LayoutDashboardIcon,
    description: "Overview & analytics",
  },
  {
    title: "Jobs",
    href: "/jobs",
    icon: BriefcaseIcon,
    description: "Manage job postings",
  },
  {
    title: "Candidates",
    href: "/candidates",
    icon: UsersIcon,
    description: "Review applications",
  },
  {
    title: "Documents",
    href: "/documents",
    icon: FileTextIcon,
    description: "Upload & manage files",
  },
];

const toolsNavItems = [
  {
    title: "Search",
    href: "/search",
    icon: SearchIcon,
    description: "Semantic document search",
  },
  {
    title: "Activity Logs",
    href: "/logs",
    icon: ClipboardListIcon,
    description: "System audit trail",
  },
];

const settingsNavItems = [
  {
    title: "Settings",
    href: "/settings",
    icon: SettingsIcon,
    description: "Account & preferences",
  },
];

export function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const getInitials = (name: string) => {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  const isActiveRoute = (href: string) => {
    if (href === "/") {
      return location.pathname === "/";
    }
    return location.pathname.startsWith(href);
  };

  const NavItem = ({
    item,
  }: {
    item: {
      title: string;
      href: string;
      icon: React.ComponentType<{ className?: string }>;
      description?: string;
      badge?: string;
    };
  }) => {
    const isActive = isActiveRoute(item.href);
    const Icon = item.icon;

    return (
      <SidebarMenuItem>
        <Tooltip>
          <TooltipTrigger
            render={
              <SidebarMenuButton
                isActive={isActive}
                className={cn(
                  "transition-all duration-200",
                  isActive && "bg-primary/10 text-primary font-medium"
                )}
                render={
                  <NavLink
                    to={item.href}
                    className="flex w-full items-center gap-3"
                  >
                    <Icon
                      className={cn(
                        "size-5 shrink-0 transition-colors",
                        isActive ? "text-primary" : "text-muted-foreground"
                      )}
                    />
                    <span className="truncate">{item.title}</span>
                    {item.badge && (
                      <span className="bg-primary/10 text-primary ml-auto flex size-5 items-center justify-center rounded text-[10px] font-semibold">
                        {item.badge}
                      </span>
                    )}
                  </NavLink>
                }
              />
            }
          />
          {isCollapsed && (
            <TooltipContent side="right" className="flex flex-col gap-1">
              <span className="font-medium">{item.title}</span>
              {item.description && (
                <span className="text-muted-foreground text-xs">
                  {item.description}
                </span>
              )}
            </TooltipContent>
          )}
        </Tooltip>
      </SidebarMenuItem>
    );
  };

  return (
    <Sidebar collapsible="icon" className="border-r">
      {/* Header / Logo */}
      <SidebarHeader className="p-4 group-data-[collapsible=icon]:p-2">
        <NavLink
          to="/"
          className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center"
        >
          <div className="bg-foreground flex size-10 shrink-0 items-center justify-center">
            <span className="text-background font-display text-base font-semibold">
              H
            </span>
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="font-display text-lg font-semibold tracking-[-0.01em]">
              Hireflow
            </span>
            <span className="text-muted-foreground text-xs">HR Platform</span>
          </div>
        </NavLink>
      </SidebarHeader>

      <SidebarSeparator />

      {/* Main Content */}
      <SidebarContent className="px-2 group-data-[collapsible=icon]:px-1">
        {/* Primary Navigation */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs font-medium group-data-[collapsible=icon]:hidden">
            Main Menu
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">
              {mainNavItems.map((item) => (
                <NavItem key={item.href} item={item} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Tools */}
        <SidebarGroup>
          <SidebarGroupLabel className="text-muted-foreground text-xs font-medium group-data-[collapsible=icon]:hidden">
            Tools
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">
              {toolsNavItems.map((item) => (
                <NavItem key={item.href} item={item} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Settings */}
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">
              {settingsNavItems.map((item) => (
                <NavItem key={item.href} item={item} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className="p-3 group-data-[collapsible=icon]:p-2">
        {/* Quick Action Button */}
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                onClick={() => navigate("/jobs/create")}
                size={isCollapsed ? "icon" : "default"}
                className={cn(
                  "w-full gap-2 shadow-sm transition-all",
                  "group-data-[collapsible=icon]:mx-auto group-data-[collapsible=icon]:size-10 group-data-[collapsible=icon]:w-10 group-data-[collapsible=icon]:rounded-full"
                )}
              >
                <PlusIcon className="size-5 shrink-0" />
                <span className="group-data-[collapsible=icon]:sr-only">
                  Post New Job
                </span>
              </Button>
            }
          />
          {isCollapsed && (
            <TooltipContent side="right">Post New Job</TooltipContent>
          )}
        </Tooltip>

        <SidebarSeparator className="my-3 group-data-[collapsible=icon]:my-2" />

        {/* User Profile */}
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                className={cn(
                  "hover:bg-accent flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors",
                  "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
                  "group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-2"
                )}
              >
                <div className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
                  {user ? getInitials(user.full_name ?? user.email) : "U"}
                </div>
                <div className="flex min-w-0 flex-1 flex-col group-data-[collapsible=icon]:hidden">
                  <span className="truncate text-sm font-medium">
                    {user?.full_name || "User"}
                  </span>
                  <span className="text-muted-foreground truncate text-xs">
                    {user?.email || ""}
                  </span>
                </div>
                <ChevronRightIcon className="text-muted-foreground size-4 group-data-[collapsible=icon]:hidden" />
              </button>
            }
          />
          <DropdownMenuContent
            align={isCollapsed ? "center" : "start"}
            side={isCollapsed ? "right" : "top"}
            className="w-56"
          >
            <div className="px-2 py-1.5">
              <p className="text-sm font-medium">{user?.full_name || "User"}</p>
              <p className="text-muted-foreground text-xs">
                {user?.email || ""}
              </p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/settings")}>
              <SettingsIcon className="mr-2 size-4" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleLogout}
              className="text-destructive focus:text-destructive"
            >
              <LogOutIcon className="mr-2 size-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
