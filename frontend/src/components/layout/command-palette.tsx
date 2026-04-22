import { useNavigate } from "react-router-dom";
import { useTheme } from "next-themes";
import {
  BriefcaseIcon,
  ClipboardListIcon,
  FileTextIcon,
  LaptopIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MoonIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  SunIcon,
  UploadIcon,
  UsersIcon,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useAuth } from "@/providers/use-auth";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { setTheme } = useTheme();

  const run = (fn: () => void) => {
    onOpenChange(false);
    fn();
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search for a command…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          <CommandItem onSelect={() => run(() => navigate("/"))}>
            <LayoutDashboardIcon className="mr-2 size-4" />
            Dashboard
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/documents"))}>
            <FileTextIcon className="mr-2 size-4" />
            Documents
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/search"))}>
            <SearchIcon className="mr-2 size-4" />
            Search
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/candidates"))}>
            <UsersIcon className="mr-2 size-4" />
            Candidates
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/jobs"))}>
            <BriefcaseIcon className="mr-2 size-4" />
            Jobs
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/logs"))}>
            <ClipboardListIcon className="mr-2 size-4" />
            Activity Logs
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/settings"))}>
            <SettingsIcon className="mr-2 size-4" />
            Settings
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Create">
          <CommandItem onSelect={() => run(() => navigate("/documents"))}>
            <UploadIcon className="mr-2 size-4" />
            Upload documents
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate("/jobs/create"))}>
            <PlusIcon className="mr-2 size-4" />
            Create job
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Appearance">
          <CommandItem
            onSelect={() => run(() => setTheme("light"))}
            keywords={["theme", "light", "appearance"]}
          >
            <SunIcon className="mr-2 size-4" />
            Theme: Light
          </CommandItem>
          <CommandItem
            onSelect={() => run(() => setTheme("dark"))}
            keywords={["theme", "dark", "appearance"]}
          >
            <MoonIcon className="mr-2 size-4" />
            Theme: Dark
          </CommandItem>
          <CommandItem
            onSelect={() => run(() => setTheme("system"))}
            keywords={["theme", "system", "appearance", "auto"]}
          >
            <LaptopIcon className="mr-2 size-4" />
            Theme: System
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Account">
          <CommandItem onSelect={() => run(handleLogout)}>
            <LogOutIcon className="mr-2 size-4" />
            Log out
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
