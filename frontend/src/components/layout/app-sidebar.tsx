import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "next-themes";
import {
  BriefcaseIcon,
  ChevronDownIcon,
  ClipboardListIcon,
  FileTextIcon,
  LaptopIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MoonIcon,
  PaletteIcon,
  SearchIcon,
  SettingsIcon,
  SunIcon,
  UsersIcon,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Logo } from "@/components/ui/logo";
import { InstallAppButton } from "@/components/layout/install-app-button";
import { useAuth } from "@/providers/use-auth";
import { cn } from "@/lib/utils";

type NavEntry = {
  title: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  description?: string;
};

// Usage-frequency order: Priya uploads + searches daily, reviews
// candidates daily, configures jobs occasionally, checks the
// dashboard a couple times a day.
const primaryNav: NavEntry[] = [
  {
    title: "Dashboard",
    href: "/",
    icon: LayoutDashboardIcon,
    description: "Overview",
  },
  {
    title: "Documents",
    href: "/documents",
    icon: FileTextIcon,
    description: "Upload & manage files",
  },
  {
    title: "Search",
    href: "/search",
    icon: SearchIcon,
    description: "Semantic document search",
  },
  {
    title: "Candidates",
    href: "/candidates",
    icon: UsersIcon,
    description: "Review applications",
  },
  {
    title: "Jobs",
    href: "/jobs",
    icon: BriefcaseIcon,
    description: "Manage job postings",
  },
];

const secondaryNav: NavEntry[] = [
  {
    title: "Activity Logs",
    href: "/logs",
    icon: ClipboardListIcon,
    description: "System audit trail",
  },
];

export function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { state } = useSidebar();
  const isCollapsed = state === "collapsed";
  const { theme, setTheme } = useTheme();

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
    dim = false,
  }: {
    item: NavEntry;
    dim?: boolean;
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
                  // Transparent left border reserves the 3px slot so
                  // the item doesn't shift when activated.
                  "border-l-[3px] border-transparent transition-colors",
                  isActive &&
                    "border-primary bg-primary/8 text-primary font-medium",
                  dim && !isActive && "text-muted-foreground"
                )}
                render={
                  <NavLink
                    to={item.href}
                    className="flex w-full items-center gap-3"
                  >
                    <Icon
                      className={cn(
                        "size-5 shrink-0",
                        isActive ? "text-primary" : "text-muted-foreground"
                      )}
                    />
                    <span className="truncate">{item.title}</span>
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
      <SidebarHeader className="p-4 group-data-[collapsible=icon]:p-2">
        <div className="flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
          <NavLink to="/" className="flex items-center gap-3">
            <Logo className="size-8 shrink-0" />
            <span className="font-display text-lg font-semibold tracking-[-0.01em] group-data-[collapsible=icon]:hidden">
              Hireflow
            </span>
          </NavLink>
          <SidebarTrigger className="text-muted-foreground ml-auto size-7 group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2 group-data-[collapsible=icon]:px-1">
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-0.5">
              {primaryNav.map((item) => (
                <NavItem key={item.href} item={item} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="mt-4">
          <SidebarGroupContent>
            <SidebarMenu className="gap-0.5">
              {secondaryNav.map((item) => (
                <NavItem key={item.href} item={item} dim />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-2 group-data-[collapsible=icon]:p-1">
        <InstallAppButton collapsed={isCollapsed} />
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                className={cn(
                  "hover:bg-muted/60 flex w-full items-center gap-3 p-2 text-left transition-colors",
                  "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
                  "group-data-[collapsible=icon]:justify-center"
                )}
              >
                <div className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
                  {user ? getInitials(user.full_name ?? user.email) : "U"}
                </div>
                <span className="truncate text-sm font-medium group-data-[collapsible=icon]:hidden">
                  {user?.full_name || "User"}
                </span>
                <ChevronDownIcon className="text-muted-foreground ml-auto size-4 group-data-[collapsible=icon]:hidden" />
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
              <p className="text-muted-foreground truncate text-xs">
                {user?.email || ""}
              </p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate("/settings")}>
              <SettingsIcon className="mr-2 size-4" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <PaletteIcon className="mr-2 size-4" />
                Theme
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuRadioGroup
                  value={theme ?? "system"}
                  onValueChange={setTheme}
                >
                  <DropdownMenuRadioItem value="light">
                    <SunIcon className="mr-2 size-4" />
                    Light
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="dark">
                    <MoonIcon className="mr-2 size-4" />
                    Dark
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="system">
                    <LaptopIcon className="mr-2 size-4" />
                    System
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
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
      <SidebarRail />
    </Sidebar>
  );
}
