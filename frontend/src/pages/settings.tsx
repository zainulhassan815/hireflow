import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { useTheme } from "next-themes";
import { LaptopIcon, MoonIcon, SunIcon } from "lucide-react";

import { changePassword, updateProfile } from "@/api";
import { EmailConnection } from "@/components/settings/email-connection";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Typography } from "@/components/ui/typography";
import { useAuth } from "@/providers/use-auth";
import { extractApiError } from "@/lib/api-errors";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const THEME_OPTIONS = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
  { value: "system", label: "System", Icon: LaptopIcon },
] as const;

const GMAIL_ERROR_MESSAGES: Record<string, string> = {
  denied: "Gmail connection cancelled.",
  missing_params: "Gmail callback was missing required parameters.",
  invalid_state: "Gmail connection expired. Please try again.",
  exchange_failed: "Could not complete Gmail OAuth. Please try again.",
};

export function SettingsPage() {
  const { user } = useAuth();
  // next-themes resolves `theme === "system"` to the OS value via
  // `resolvedTheme`, but the stored preference is what the picker
  // should reflect. Fall back to "system" until mount to avoid an
  // SSR/CSR mismatch on first paint.
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const activeTheme = mounted ? (theme ?? "system") : "system";

  const [fullName, setFullName] = React.useState(user?.full_name ?? "");
  const [email, setEmail] = React.useState(user?.email ?? "");
  const [savingProfile, setSavingProfile] = React.useState(false);

  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [savingPassword, setSavingPassword] = React.useState(false);

  const [searchParams, setSearchParams] = useSearchParams();
  React.useEffect(() => {
    const result = searchParams.get("gmail");
    if (!result) return;
    if (result === "connected") {
      toast.success("Gmail connected");
    } else if (result === "error") {
      const reason = searchParams.get("reason") ?? "";
      toast.error(GMAIL_ERROR_MESSAGES[reason] ?? "Gmail connection failed.");
    }
    const next = new URLSearchParams(searchParams);
    next.delete("gmail");
    next.delete("reason");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    const { error } = await updateProfile({
      body: {
        full_name: fullName || undefined,
        email: email !== user?.email ? email : undefined,
      },
    });
    setSavingProfile(false);
    if (error) {
      toast.error(extractApiError(error).message);
      return;
    }
    toast.success("Profile updated");
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setSavingPassword(true);
    const { error } = await changePassword({
      body: {
        current_password: currentPassword,
        new_password: newPassword,
      },
    });
    setSavingPassword(false);
    if (error) {
      toast.error(extractApiError(error).message);
      return;
    }
    toast.success("Password changed");
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Typography variant="h3">Settings</Typography>
        <Typography variant="muted">
          Manage your account and preferences
        </Typography>
      </div>

      <div className="grid gap-6">
        {/* Profile */}
        <Card>
          <CardHeader>
            <Typography variant="h5">Profile</Typography>
            <Typography variant="muted">Your personal information</Typography>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="name">Full Name</Label>
                <Input
                  id="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Input value={user?.role ?? ""} disabled className="capitalize" />
            </div>
            <Button onClick={handleSaveProfile} disabled={savingProfile}>
              {savingProfile ? "Saving..." : "Save Changes"}
            </Button>
          </CardContent>
        </Card>

        <Separator />

        {/* Appearance */}
        <Card>
          <CardHeader>
            <Typography variant="h5">Appearance</Typography>
            <Typography variant="muted">
              Theme preference — applies to this browser
            </Typography>
          </CardHeader>
          <CardContent>
            <div
              role="radiogroup"
              aria-label="Theme"
              className="flex flex-wrap gap-2"
            >
              {THEME_OPTIONS.map(({ value, label, Icon }) => {
                const selected = activeTheme === value;
                return (
                  <Button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    variant={selected ? "default" : "outline"}
                    onClick={() => setTheme(value)}
                    className={cn("min-w-28 justify-start")}
                  >
                    <Icon className="size-4" data-icon="inline-start" />
                    {label}
                  </Button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Separator />

        {/* Password */}
        <Card>
          <CardHeader>
            <Typography variant="h5">Change Password</Typography>
            <Typography variant="muted">Update your password</Typography>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="current-password">Current Password</Label>
                <Input
                  id="current-password"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="new-password">New Password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    minLength={8}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Confirm Password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </div>
              </div>
              <Button type="submit" disabled={savingPassword}>
                {savingPassword ? "Changing..." : "Change Password"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Separator />

        <EmailConnection />
      </div>
    </div>
  );
}
