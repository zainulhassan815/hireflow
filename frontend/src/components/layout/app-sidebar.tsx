import { NavLink, useLocation } from "react-router-dom";
import {
  BriefcaseIcon,
  LayoutDashboardIcon,
  PlusIcon,
  SettingsIcon,
  SparklesIcon,
  UsersIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
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
  SidebarSeparator,
} from "@/components/ui/sidebar";

const navItems = [
  {
    title: "Dashboard",
    href: "/",
    icon: LayoutDashboardIcon,
  },
  {
    title: "Jobs",
    href: "/jobs",
    icon: BriefcaseIcon,
  },
  {
    title: "Candidates",
    href: "/candidates",
    icon: UsersIcon,
  },
  {
    title: "AI Analytics",
    href: "/analytics",
    icon: SparklesIcon,
  },
  {
    title: "Settings",
    href: "/settings",
    icon: SettingsIcon,
  },
];

export function AppSidebar() {
  const location = useLocation();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="p-4">
        <SidebarMenu>
          <SidebarMenuItem>
            <NavLink to="/" className="flex items-center gap-3">
              <div className="bg-primary flex size-8 items-center justify-center">
                <span className="text-sm font-bold text-white">S</span>
              </div>
              <span className="text-lg font-semibold group-data-[collapsible=icon]:hidden">
                ScreenAI
              </span>
            </NavLink>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-0.5">
              {navItems.map((item) => {
                const isActive = location.pathname === item.href;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton isActive={isActive} tooltip={item.title}>
                      <NavLink
                        to={item.href}
                        className="flex w-full items-center gap-3"
                      >
                        <item.icon className="size-4" />
                        <span className="text-sm">{item.title}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4">
        <SidebarSeparator className="mb-4" />
        <Button className="w-full gap-2 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-0">
          <PlusIcon className="size-4" />
          <span className="group-data-[collapsible=icon]:hidden">
            Post New Job
          </span>
        </Button>
        <div className="mt-4 flex items-center gap-3 group-data-[collapsible=icon]:justify-center">
          <div className="bg-muted flex size-8 items-center justify-center text-xs font-medium">
            AM
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="text-sm font-medium">Alex Morgan</span>
            <span className="text-muted-foreground text-xs">Recruiter</span>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
